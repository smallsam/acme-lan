"""Cisco IOS / IOS-XE deploy plugin: install certificates via the device CLI.

IOS has no filesystem you can just drop a PEM onto and no SSH exec channel — certificates
go in through interactive ``crypto pki`` commands on a terminal. Both acme-lan modes are
supported:

* **device** (preferred) — the switch generates the keypair and a CSR
  (``crypto pki enroll``); acme-lan gets it signed and pushes back only the certificate
  with ``crypto pki import``. The private key never leaves the device.
* **local** — acme-lan generates the key and CSR, wraps both into a PKCS#12 and imports it
  with ``crypto pki import ... pkcs12 terminal``.

Two IOS defaults would get a CSR rejected by a public CA, so this plugin overrides both:
``hash sha256`` (IOS otherwise signs the request with SHA-1) and ``subject-alt-name``
(IOS otherwise emits a CN-only CSR, and CAs such as Let's Encrypt require a dNSName SAN).

Saving the configuration is **off** by default (``write_memory``): certificate and HTTPS
changes stay in the running config and are lost on reload unless you opt in. Note that IOS
persists generated RSA keys to its private-config regardless of that setting.
"""

from __future__ import annotations

import base64
import re
import secrets
import time
from typing import Any

from .base import DeployContext, DeployPlugin, DeployResult, PluginField
from .iosshell import Channel, OpenSshPtyChannel, ParamikoChannel, ShellError

# Device prompt: "sfsw#", "sfsw>", "sfsw(config)#", "sfsw(ca-trustpoint)#".
PROMPT = r"[\r\n][\w.\-]+(?:\([^)\r\n]*\))?[>#] ?$"
# IOS reports failures inline; these mean the command did not take effect.
ERROR_MARKERS = (
    "% Invalid input",
    "% Incomplete command",
    "% Ambiguous command",
    "% Error",
    "%Error",
    "% Failed",
    "% Cannot",
    "% Unable",
    "% Trustpoint not",
)

BEGIN_CSR = "-----BEGIN CERTIFICATE REQUEST-----"
END_CSR = "-----END CERTIFICATE REQUEST-----"

# Questions IOS asks while ingesting a PKCS#12 that carries CA certificates. Saying yes to
# the hierarchy question makes IOS keep the intermediates, so the device can present a full
# chain to clients instead of just its own certificate.
#
# Each pattern must match a *distinct* prompt. IOS wraps this one over two lines
# ("...for CAs higher in" / "% the hierarchy? [yes/no]:"), so matching both halves would
# answer it twice and the surplus "yes" lands on the config prompt as a bogus command.
PKCS12_ANSWERS: tuple[tuple[str, str], ...] = (
    (r"hierarchy\? \[yes/no\]:", "yes"),
    (r"accept this certificate\? \[yes/no\]:", "yes"),
)


def split_pem_certificates(pem_text: str) -> list[str]:
    """Split a PEM bundle into individual certificate blocks, in order."""
    return [
        block.strip() + "\n"
        for block in re.findall(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
            pem_text,
            re.DOTALL,
        )
    ]


def _issuer_cn(cert_pem: str) -> str:
    """Best-effort issuer CN of a PEM certificate, for error messages."""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID

        cert = x509.load_pem_x509_certificate(cert_pem.encode())
        attrs = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
        return attrs[0].value if attrs else cert.issuer.rfc4514_string()
    except Exception:  # noqa: BLE001 - diagnostics only
        return "unknown"


def extract_csr(output: str) -> str:
    """Pull the PEM certificate request out of ``crypto pki enroll`` terminal output."""
    if BEGIN_CSR not in output or END_CSR not in output:
        raise ShellError(f"no CSR found in the enroll output:\n{output.strip()[-800:]}")
    body = output[output.index(BEGIN_CSR) : output.index(END_CSR) + len(END_CSR)]
    # The pty leaves carriage returns behind, and IOS pads with blank lines.
    lines = [line.strip() for line in body.replace("\r", "").splitlines() if line.strip()]
    return "\n".join(lines) + "\n"


class IosSession:
    """A logged-in IOS CLI session with prompt-aware command execution."""

    def __init__(self, channel: Channel, *, password: str | None, paste_delay: float = 0.03):
        self.chan = channel
        self.password = password
        self.paste_delay = paste_delay
        self.in_config = False

    def drain(
        self, answers: tuple[tuple[str, str], ...] = (), timeout: float = 60.0
    ) -> str:
        """Read until the prompt settles, answering interactive questions on the way."""
        out, cursor = "", 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.chan.read(0.4)
            out += chunk
            tail = out[cursor:]
            for pattern, response in answers:
                match = re.search(pattern, tail)
                if match:
                    self.chan.send(response + "\n")
                    cursor += match.end()
                    break
            else:
                # Only accept the prompt once output has gone quiet, so a prompt echoed
                # mid-command doesn't look like completion.
                if not chunk and re.search(PROMPT, out[cursor:]):
                    return out
        raise ShellError(f"timed out waiting for the IOS prompt; last output:\n{out[-1500:]}")

    def _check(self, command: str, out: str) -> str:
        for marker in ERROR_MARKERS:
            if marker in out:
                raise ShellError(f"IOS rejected {command!r}: {out.strip()[-400:]}")
        return out

    def run(
        self,
        command: str,
        *,
        answers: tuple[tuple[str, str], ...] = (),
        timeout: float = 60.0,
        allow_errors: bool = False,
    ) -> str:
        """Run a command that returns to the prompt when it's done."""
        self.chan.send(command + "\n")
        out = self.drain(answers, timeout)
        return out if allow_errors else self._check(command, out)

    def send_expect(self, command: str, pattern: str, timeout: float = 60.0) -> str:
        """Run a command that stops at a prompt for input rather than returning to the CLI."""
        self.chan.send(command + "\n")
        out = self.chan.expect(pattern + "|" + "|".join(re.escape(m) for m in ERROR_MARKERS),
                               timeout=timeout)
        return self._check(command, out)

    def login(self, timeout: float = 40.0) -> str:
        out = self.chan.expect(r"(?i)password:|" + PROMPT, timeout=timeout)
        if re.search(r"(?i)password:", out):
            if self.password is None:
                raise ShellError("the device asked for a password but the credential has none")
            self.chan.send(self.password + "\n")
            out = self.chan.expect(r"(?i)password:|denied|" + PROMPT, timeout=timeout)
            if re.search(r"(?i)password:|denied", out):
                raise ShellError("IOS login failed (password rejected)")
        # Privileged exec is required for crypto pki; escalate if we landed in user mode.
        if out.rstrip().endswith(">"):
            self.chan.send("enable\n")
            out = self.chan.expect(r"(?i)password:|" + PROMPT, timeout=timeout)
            if re.search(r"(?i)password:", out):
                self.chan.send((self.password or "") + "\n")
                out = self.chan.expect(PROMPT, timeout=timeout)
            if out.rstrip().endswith(">"):
                raise ShellError(
                    "could not reach privileged exec mode; the account needs privilege 15 "
                    "or an enable password matching the login credential"
                )
        # No paging, and don't let the device wrap the PEM output we have to parse.
        self.run("terminal length 0", allow_errors=True, timeout=20)
        self.run("terminal width 0", allow_errors=True, timeout=20)
        return out

    def configure(self) -> None:
        if not self.in_config:
            self.run("configure terminal", timeout=30)
            self.in_config = True

    def end_config(self) -> None:
        if self.in_config:
            self.run("end", allow_errors=True, timeout=30)
            self.in_config = False

    def paste_block(
        self,
        text: str,
        *,
        terminator: str = "quit",
        answers: tuple[tuple[str, str], ...] = (),
        timeout: float = 120.0,
    ) -> str:
        """Feed a PEM/base64 block line by line, then the terminator IOS waits for.

        Returns the device's response and raises on any IOS error marker — pasted blocks
        fail loudly here (e.g. "% Error in saving certificate"), and swallowing that turns
        into a confusing failure several commands later.
        """
        for line in text.strip().splitlines():
            self.chan.send(line.rstrip() + "\n")
            time.sleep(self.paste_delay)
        self.chan.send(terminator + "\n")
        out = self.drain(answers, timeout)
        return self._check("pasted certificate block", out)


class CiscoIosDeployPlugin(DeployPlugin):
    name = "cisco_ios"
    supports_csr_retrieval = True
    fields = [
        PluginField(
            "trustpoint", "Trustpoint name", required=True, modes=("device", "local"),
            placeholder="ACMELAN", help="IOS crypto pki trustpoint to create/use.",
        ),
        PluginField(
            "key_label", "RSA key label", modes=("device", "local"),
            placeholder="defaults to the trustpoint name",
            help="Label for the device keypair (device mode generates it).",
        ),
        PluginField(
            "key_bits", "RSA modulus", type="number", modes=("device",), placeholder="2048",
            help="Key size generated on the device (2048 minimum for public CAs).",
        ),
        PluginField(
            "hash_algorithm", "Request hash", modes=("device",), placeholder="sha256",
            help="Signature hash for the CSR. IOS defaults to sha1, which public CAs reject.",
        ),
        PluginField(
            "apply_to_https", "Apply to HTTPS server", type="checkbox",
            modes=("device", "local"),
            help="Point 'ip http secure-trustpoint' at this trustpoint and enable "
            "'ip http secure-server'.",
        ),
        PluginField(
            "write_memory", "Save configuration", type="checkbox", modes=("device", "local"),
            help="Run 'write memory' after installing. OFF by default: changes stay in the "
            "running config and are lost on reload (IOS still persists generated RSA keys).",
        ),
        PluginField(
            "legacy_ssh", "Legacy SSH algorithms", type="checkbox", modes=("device", "local"),
            help="For older IOS that only offers ssh-rsa / diffie-hellman-group*-sha1 / "
            "aes256-cbc. Uses the system ssh client, which still supports them.",
        ),
        PluginField(
            "regenerate_key", "Regenerate key", type="checkbox", modes=("device",),
            help="Replace an existing keypair with the same label instead of reusing it.",
        ),
        PluginField(
            "pkcs12_legacy_encryption", "Legacy PKCS#12 encryption", type="checkbox",
            modes=("local",),
            help="Seal the PKCS#12 with 3DES/SHA-1 so older IOS can read it (default on).",
        ),
        PluginField(
            "ssh_options", "Extra ssh options", modes=("device", "local"),
            placeholder="-o MACs=+hmac-sha1",
            help="Extra options for the system ssh client (also forces that transport).",
        ),
        PluginField(
            "port", "SSH port", type="number", modes=("device", "local"), placeholder="22",
        ),
    ]

    # --- helpers ---
    @staticmethod
    def _bool(config: dict[str, Any], key: str, default: bool = False) -> bool:
        value = config.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def _open(self, ctx: DeployContext) -> IosSession:
        cfg = ctx.config
        if ctx.credential is None:
            raise ShellError("cisco_ios plugin requires a credential (device login)")
        port = int(cfg.get("port") or 22)
        is_key = ctx.credential.kind == "ssh_key"
        password = None if is_key else ctx.credential.secret
        pkey = ctx.credential.secret if is_key else None
        legacy = self._bool(cfg, "legacy_ssh")
        extra = tuple(str(cfg.get("ssh_options") or "").split())

        channel: Channel
        if legacy or extra:
            # paramiko 5 dropped ssh-rsa and the SHA-1 kex methods entirely, so legacy gear
            # can only be reached through the system ssh client.
            channel = OpenSshPtyChannel(
                ctx.host.address, port, ctx.credential.username,
                password=password, pkey_pem=pkey, legacy=legacy, extra_options=extra,
            )
        else:
            channel = ParamikoChannel(
                ctx.host.address, port, ctx.credential.username,
                password=password, pkey_pem=pkey,
            )
        session = IosSession(channel, password=password)
        session.login()
        return session

    def _trustpoint(self, ctx: DeployContext) -> str:
        trustpoint = str(ctx.config.get("trustpoint") or "").strip()
        if not trustpoint:
            raise ShellError("cisco_ios plugin requires 'trustpoint'")
        return trustpoint

    def _key_label(self, ctx: DeployContext) -> str:
        return str(ctx.config.get("key_label") or self._trustpoint(ctx)).strip()

    def _apply_https(self, session: IosSession, trustpoint: str) -> None:
        session.configure()
        session.run(f"ip http secure-trustpoint {trustpoint}", timeout=45)
        session.run("ip http secure-server", timeout=45)

    def _save(self, session: IosSession, config: dict[str, Any]) -> str:
        if not self._bool(config, "write_memory"):
            return " (running-config only; not saved to startup-config)"
        session.end_config()
        session.run(
            "write memory",
            answers=(
                (r"\[confirm\]", ""),
                (r"Destination filename \[startup-config\]\?", ""),
            ),
            timeout=180,
        )
        return " (configuration saved)"

    # --- mode 1: CSR from the device (key never leaves it) ---
    def fetch_csr(self, ctx: DeployContext) -> str:
        trustpoint = self._trustpoint(ctx)
        key_label = self._key_label(ctx)
        domains = [d for d in (ctx.host.domains or []) if d]
        if not domains:
            raise ShellError("the host has no domains to request a certificate for")
        bits = int(ctx.config.get("key_bits") or 2048)
        hash_algorithm = str(ctx.config.get("hash_algorithm") or "sha256").strip()

        session = self._open(ctx)
        try:
            existing = session.run(
                "show crypto key mypubkey rsa | include Key name", timeout=45, allow_errors=True
            )
            have_key = re.search(rf"Key name:\s*{re.escape(key_label)}\s*$", existing, re.M)
            regenerate = self._bool(ctx.config, "regenerate_key")
            session.configure()
            if not have_key or regenerate:
                session.run(
                    f"crypto key generate rsa general-keys label {key_label} modulus {bits}",
                    answers=((r"want to replace them\? \[yes/no\]:", "yes"),),
                    timeout=300,
                )
            session.run(f"crypto pki trustpoint {trustpoint}", timeout=45)
            session.run("enrollment terminal pem", timeout=30)
            # IOS signs the request with SHA-1 unless told otherwise; public CAs reject that.
            session.run(f"hash {hash_algorithm}", timeout=30)
            session.run(f"subject-name CN={domains[0]}", timeout=30)
            # Without an explicit SAN the CSR carries only a CN, which CAs such as Let's
            # Encrypt reject. Support for several names here depends on the IOS build.
            session.run(f"subject-alt-name {','.join(domains)}", timeout=30)
            session.run(f"rsakeypair {key_label}", timeout=30)
            session.run("revocation-check none", timeout=30)
            # Drops the unstructuredName IOS otherwise adds from the device FQDN.
            session.run("fqdn none", timeout=30, allow_errors=True)
            session.run("exit", timeout=30)

            out = session.run(
                f"crypto pki enroll {trustpoint}",
                answers=(
                    (r"serial number in the subject name\? \[yes/no\]:", "no"),
                    (r"IP address in the subject name\? \[no\]:", "no"),
                    (r"Display Certificate Request to terminal\? \[yes/no\]:", "yes"),
                    (r"Redisplay enrollment request\? \[yes/no\]:", "no"),
                ),
                timeout=240,
            )
            return extract_csr(out)
        finally:
            try:
                session.end_config()
            finally:
                session.chan.close()

    def install_cert(self, ctx: DeployContext) -> DeployResult:
        """Authenticate the issuing CA, then import the signed certificate."""
        try:
            trustpoint = self._trustpoint(ctx)
            blocks = split_pem_certificates(ctx.fullchain_pem)
            if not blocks:
                return DeployResult(False, "the issued chain contained no certificates")
            leaf, cas = blocks[0], blocks[1:]
            if not cas:
                return DeployResult(
                    False,
                    "the issued chain has no CA certificate; IOS must authenticate the "
                    "issuing CA before it will import a device certificate",
                )
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"cisco_ios configuration error: {exc}")
        try:
            session = self._open(ctx)
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"cisco_ios connect failed: {exc}")
        try:
            session.configure()
            # IOS authenticates one CA per trustpoint: use the leaf's direct issuer.
            session.send_expect(
                f"crypto pki authenticate {trustpoint}",
                r"base 64 encoded CA cert|End with a blank line",
                timeout=90,
            )
            try:
                session.paste_block(cas[0], answers=PKCS12_ANSWERS, timeout=120)
            except ShellError as exc:
                if "saving certificate" in str(exc):
                    # IOS anchors a trustpoint on a self-signed CA. Public chains often
                    # ship none (Let's Encrypt's chain ends at a cross-signed root), so it
                    # refuses the intermediate outright.
                    return DeployResult(
                        False,
                        "IOS refused to trust the issuing CA: it anchors a trustpoint on a "
                        "self-signed certificate, and this chain contains none (its top CA "
                        f"is {_issuer_cn(cas[-1])!r}, itself issued by another CA). Either "
                        "switch this host to the 'local' CSR mode, which imports a PKCS#12 "
                        "carrying the whole chain and needs no CA authentication, or "
                        "pre-authenticate a trustpoint holding the CA's self-signed root "
                        f"and reference it with 'chain-validation continue'. IOS said: {exc}",
                    )
                raise

            session.send_expect(
                f"crypto pki import {trustpoint} certificate",
                r"base 64 encoded certificate|End with a blank line",
                timeout=90,
            )
            out = session.paste_block(leaf, timeout=180)
            if "successfully imported" not in out.lower():
                return DeployResult(
                    False, f"certificate import was not confirmed: {out.strip()[-400:]}"
                )

            detail = f"imported into trustpoint {trustpoint}"
            if self._bool(ctx.config, "apply_to_https", default=True):
                self._apply_https(session, trustpoint)
                detail += "; HTTPS server using it"
            detail += self._save(session, ctx.config)
            return DeployResult(True, detail)
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"cisco_ios install failed: {exc}")
        finally:
            try:
                session.end_config()
            finally:
                session.chan.close()

    # --- mode 2: acme-lan holds the key (PKCS#12 import) ---
    def deploy(self, ctx: DeployContext) -> DeployResult:
        if not ctx.private_key_pem:
            return DeployResult(False, "local mode needs the private key")
        # A throwaway transport password for the bundle: IOS requires one, and it is only
        # ever passed on this session (never stored).
        password = secrets.token_urlsafe(18)
        try:
            trustpoint = self._trustpoint(ctx)
            p12_b64 = self.build_pkcs12(ctx, password)
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"could not build the PKCS#12 bundle: {exc}")
        try:
            session = self._open(ctx)
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"cisco_ios connect failed: {exc}")
        try:
            session.configure()
            session.send_expect(
                f"crypto pki import {trustpoint} pkcs12 terminal password {password}",
                r"base 64 encoded pkcs12|End with a blank line",
                timeout=90,
            )
            out = session.paste_block(p12_b64, answers=PKCS12_ANSWERS, timeout=300)
            if "failed" in out.lower():
                return DeployResult(False, f"PKCS#12 import failed: {out.strip()[-400:]}")
            if "imported pkcs12 file successfully" not in out.lower():
                return DeployResult(
                    False, f"PKCS#12 import was not confirmed: {out.strip()[-400:]}"
                )

            detail = f"PKCS#12 imported into trustpoint {trustpoint}"
            if self._bool(ctx.config, "apply_to_https", default=True):
                self._apply_https(session, trustpoint)
                detail += "; HTTPS server using it"
            detail += self._save(session, ctx.config)
            return DeployResult(True, detail)
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"cisco_ios deploy failed: {exc}")
        finally:
            try:
                session.end_config()
            finally:
                session.chan.close()

    def build_pkcs12(self, ctx: DeployContext, password: str) -> str:
        """Wrap key + chain into a base64 PKCS#12 that IOS can import from the terminal."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.serialization import pkcs12

        if not ctx.private_key_pem:
            raise ValueError("no private key to wrap")
        key = serialization.load_pem_private_key(ctx.private_key_pem.encode(), password=None)
        certs = [
            x509.load_pem_x509_certificate(block.encode())
            for block in split_pem_certificates(ctx.fullchain_pem)
        ]
        if not certs:
            raise ValueError("the issued chain contained no certificates")

        secret = password.encode()
        if self._bool(ctx.config, "pkcs12_legacy_encryption", default=True):
            # Older IOS only reads PKCS#12 sealed with the legacy 3DES/SHA-1 algorithms.
            encryption = (
                serialization.PrivateFormat.PKCS12.encryption_builder()
                .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC)
                .hmac_hash(hashes.SHA1())
                .build(secret)
            )
        else:
            encryption = serialization.BestAvailableEncryption(secret)
        blob = pkcs12.serialize_key_and_certificates(
            name=self._trustpoint(ctx).encode(),
            key=key,
            cert=certs[0],
            cas=certs[1:] or None,
            encryption_algorithm=encryption,
        )
        # Wrap at 64 columns: the IOS terminal truncates long input lines, and a single
        # multi-kilobyte base64 line arrives corrupted ("BER decode failed").
        b64 = base64.b64encode(blob).decode()
        return "\n".join(b64[i : i + 64] for i in range(0, len(b64), 64))

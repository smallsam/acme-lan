"""Tests for the Cisco IOS deploy plugin, driven by a scripted fake CLI.

The fake channel replays realistic IOS output (captured from a Catalyst C6800IA) so the
prompt handling, CSR extraction and command sequence are covered without a device.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from acme_lan.deploy.base import DeployContext
from acme_lan.deploy.cisco_ios import (
    CiscoIosDeployPlugin,
    IosSession,
    extract_csr,
    split_pem_certificates,
)
from acme_lan.deploy.iosshell import Channel, ShellError
from acme_lan.models import ManagedHost

CSR_PEM = """-----BEGIN CERTIFICATE REQUEST-----
MIICnTCCAYUCAQAwNzEbMBkGA1UEAxMScHJvYmUuc21hbGxzYW0ubmV0
-----END CERTIFICATE REQUEST-----"""


class FakeChannel(Channel):
    """Replays canned responses keyed by the command that was sent."""

    def __init__(self, responses: list[tuple[str, str]], prompt: str = "\r\nsfsw#") -> None:
        self.responses = responses
        self.prompt = prompt
        self.sent: list[str] = []
        self._pending = "\r\nsfsw#"  # banner: already logged in at privileged exec
        self.closed = False

    def send(self, data: str) -> None:
        self.sent.append(data.rstrip("\n"))
        line = data.strip()
        for pattern, reply in self.responses:
            if re.search(pattern, line):
                self._pending += reply
                return
        # Unknown command: echo it and return to the prompt.
        self._pending += f"\r\n{line}{self.prompt}"

    def read(self, timeout: float) -> str:
        out, self._pending = self._pending, ""
        return out

    def close(self) -> None:
        self.closed = True


def _host(**kwargs) -> ManagedHost:
    return ManagedHost(
        name="sfsw", domains=["sfsw.lan.test"], address="192.0.2.10", **kwargs
    )


def _ctx(config: dict, *, fullchain: str = "", key_pem: str | None = None) -> DeployContext:
    from acme_lan.credentials import DecryptedCredential

    return DeployContext(
        host=_host(),
        fullchain_pem=fullchain,
        private_key_pem=key_pem,
        credential=DecryptedCredential(kind="password", username="admin", secret="pw"),
        config=config,
    )


def _chain_with_key(n: int = 2) -> tuple[str, str]:
    """A leaf plus ``n-1`` CA certificates as a PEM chain, with the leaf's key PEM.

    PKCS#12 requires the key to match the leaf, so the two are generated together.
    """
    out: list[str] = []
    leaf_key_pem = ""
    for i in range(n):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"cert{i}")]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"issuer{i}")]))
            .public_key(key.public_key())
            .serial_number(1000 + i)
            .not_valid_before(datetime(2026, 1, 1, tzinfo=UTC))
            .not_valid_after(datetime(2027, 1, 1, tzinfo=UTC))
            .sign(key, hashes.SHA256())
        )
        out.append(cert.public_bytes(serialization.Encoding.PEM).decode())
        if i == 0:
            leaf_key_pem = key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode()
    return "".join(out), leaf_key_pem


def _chain(n: int = 2) -> str:
    return _chain_with_key(n)[0]


# --- pure helpers ---


def test_split_pem_certificates_keeps_order():
    chain = _chain(3)
    blocks = split_pem_certificates(chain)
    assert len(blocks) == 3
    assert all(b.startswith("-----BEGIN CERTIFICATE-----") for b in blocks)
    # The first block is the leaf, i.e. the first cert in the input.
    assert blocks[0].strip() == chain.split("-----END CERTIFICATE-----")[0].strip() + (
        "\n-----END CERTIFICATE-----"
    )


def test_extract_csr_strips_pty_noise():
    raw = (
        "crypto pki enroll TP\r\n% Start certificate enrollment\r\n"
        "Certificate Request follows:\r\n\r\n"
        + CSR_PEM.replace("\n", "\r\n")
        + "\r\n\r\n---End - This line not part of the certificate request---\r\n"
        "Redisplay enrollment request? [yes/no]: no\r\nsfsw(config)#"
    )
    csr = extract_csr(raw)
    assert "\r" not in csr
    assert csr.startswith("-----BEGIN CERTIFICATE REQUEST-----")
    assert csr.strip().endswith("-----END CERTIFICATE REQUEST-----")
    # Round-trips as a real CSR structure (header/footer intact, no stray blank lines).
    assert "\n\n" not in csr


def test_extract_csr_raises_when_absent():
    with pytest.raises(ShellError, match="no CSR"):
        extract_csr("crypto pki enroll TP\r\n% Trustpoint not found\r\nsfsw(config)#")


# --- session behaviour ---


def test_run_raises_on_ios_error_marker():
    chan = FakeChannel([(r"bogus", "\r\nbogus\r\n% Invalid input detected\r\nsfsw#")])
    session = IosSession(chan, password="pw", paste_delay=0)
    with pytest.raises(ShellError, match="Invalid input"):
        session.run("bogus", timeout=5)


def test_run_answers_interactive_prompts_until_prompt_returns():
    chan = FakeChannel(
        [
            (
                r"crypto key generate",
                "\r\ncrypto key generate\r\n% You already have RSA keys defined named x."
                "\r\nDo you really want to replace them? [yes/no]:",
            ),
            (r"^yes$", "\r\n% Generating 2048 bit RSA keys ...[OK]\r\nsfsw(config)#"),
        ]
    )
    session = IosSession(chan, password="pw", paste_delay=0)
    out = session.run(
        "crypto key generate rsa general-keys label k modulus 2048",
        answers=((r"want to replace them\? \[yes/no\]:", "yes"),),
        timeout=10,
    )
    assert "[OK]" in out
    assert "yes" in chan.sent


def test_paste_block_sends_each_line_then_quit():
    chan = FakeChannel([])
    session = IosSession(chan, password="pw", paste_delay=0)
    session.paste_block("line-one\nline-two\n")
    assert chan.sent == ["line-one", "line-two", "quit"]


# --- device mode ---


def _enroll_responses() -> list[tuple[str, str]]:
    return [
        (r"show crypto key mypubkey", "\r\nKey name: other\r\nsfsw#"),
        (r"configure terminal", "\r\nsfsw(config)#"),
        (r"crypto key generate", "\r\n% Generating 2048 bit keys ...[OK]\r\nsfsw(config)#"),
        (r"crypto pki trustpoint", "\r\nsfsw(ca-trustpoint)#"),
        (r"^(enrollment|hash|subject-name|subject-alt-name|rsakeypair|revocation-check|fqdn)",
         "\r\nsfsw(ca-trustpoint)#"),
        (r"^exit$", "\r\nsfsw(config)#"),
        (
            r"crypto pki enroll",
            "\r\n% Start certificate enrollment ..\r\n"
            "% Include the router serial number in the subject name? [yes/no]:",
        ),
        (r"^no$", "\r\n% Include an IP address in the subject name? [no]:"),
        (r"^n$", "\r\nDisplay Certificate Request to terminal? [yes/no]:"),
        (r"^end$", "\r\nsfsw#"),
    ]


def test_fetch_csr_drives_enrollment_and_sets_sha256_and_san():
    """The two IOS defaults that break public CAs must be overridden."""
    responses = [
        (r"show crypto key mypubkey", "\r\nKey name: other\r\nsfsw#"),
        (r"terminal (length|width)", "\r\nsfsw#"),
        (r"configure terminal", "\r\nsfsw(config)#"),
        (r"crypto key generate", "\r\n% Generating keys ...[OK]\r\nsfsw(config)#"),
        (r"crypto pki trustpoint", "\r\nsfsw(ca-trustpoint)#"),
        (
            r"^(enrollment terminal pem|hash |subject-name |subject-alt-name |rsakeypair "
            r"|revocation-check |fqdn )",
            "\r\nsfsw(ca-trustpoint)#",
        ),
        (r"^exit$", "\r\nsfsw(config)#"),
        (
            r"crypto pki enroll",
            "\r\n% Start certificate enrollment ..\r\n"
            "% Include the router serial number in the subject name? [yes/no]: no\r\n"
            "% Include an IP address in the subject name? [no]: no\r\n"
            "Display Certificate Request to terminal? [yes/no]: yes\r\n"
            "Certificate Request follows:\r\n\r\n"
            + CSR_PEM.replace("\n", "\r\n")
            + "\r\n\r\n---End - This line not part of the certificate request---\r\n"
            "Redisplay enrollment request? [yes/no]: no\r\nsfsw(config)#",
        ),
        (r"^end$", "\r\nsfsw#"),
    ]
    chan = FakeChannel(responses)
    plugin = CiscoIosDeployPlugin()
    session_holder = {}

    def _open(ctx):
        session = IosSession(chan, password="pw", paste_delay=0)
        session_holder["s"] = session
        return session

    plugin._open = _open  # type: ignore[method-assign]
    csr = plugin.fetch_csr(_ctx({"trustpoint": "ACMELAN", "key_bits": 2048}))

    assert csr.startswith("-----BEGIN CERTIFICATE REQUEST-----")
    sent = chan.sent
    assert "hash sha256" in sent, "IOS defaults to sha1, which public CAs reject"
    assert "subject-alt-name sfsw.lan.test" in sent, "a CN-only CSR is rejected by LE"
    assert "subject-name CN=sfsw.lan.test" in sent
    assert "enrollment terminal pem" in sent
    assert "rsakeypair ACMELAN" in sent
    # The key was missing from the device, so it must have been generated.
    assert any(s.startswith("crypto key generate rsa") for s in sent)


def test_fetch_csr_reuses_existing_key_unless_regenerate():
    responses = [
        (r"show crypto key mypubkey", "\r\nKey name: ACMELAN\r\nsfsw#"),
        (r"terminal (length|width)", "\r\nsfsw#"),
        (r"configure terminal", "\r\nsfsw(config)#"),
        (r"crypto pki trustpoint", "\r\nsfsw(ca-trustpoint)#"),
        (
            r"^(enrollment|hash |subject-name |subject-alt-name |rsakeypair "
            r"|revocation-check |fqdn )",
            "\r\nsfsw(ca-trustpoint)#",
        ),
        (r"^exit$", "\r\nsfsw(config)#"),
        (
            r"crypto pki enroll",
            "\r\nCertificate Request follows:\r\n\r\n"
            + CSR_PEM.replace("\n", "\r\n")
            + "\r\n\r\n---End---\r\nsfsw(config)#",
        ),
        (r"^end$", "\r\nsfsw#"),
    ]
    chan = FakeChannel(responses)
    plugin = CiscoIosDeployPlugin()
    plugin._open = lambda ctx: IosSession(chan, password="pw", paste_delay=0)  # type: ignore
    plugin.fetch_csr(_ctx({"trustpoint": "ACMELAN"}))
    assert not any(s.startswith("crypto key generate") for s in chan.sent)


def _install_responses(*, save: bool = False) -> list[tuple[str, str]]:
    return [
        (r"terminal (length|width)", "\r\nsfsw#"),
        (r"configure terminal", "\r\nsfsw(config)#"),
        (
            r"crypto pki authenticate",
            "\r\nEnter the base 64 encoded CA certificate.\r\n"
            "End with a blank line or the word \"quit\" on a line by itself",
        ),
        (
            r"^quit$",
            "\r\nCertificate has the following attributes:\r\n"
            "% Do you accept this certificate? [yes/no]:",
        ),
        (r"^yes$", "\r\nTrustpoint CA certificate accepted.\r\nsfsw(config)#"),
        (
            r"crypto pki import .* certificate$",
            "\r\nEnter the base 64 encoded certificate.\r\n"
            "End with a blank line or the word \"quit\" on a line by itself",
        ),
        (r"ip http secure-trustpoint|ip http secure-server", "\r\nsfsw(config)#"),
        (r"^end$", "\r\nsfsw#"),
        (r"write memory", "\r\nBuilding configuration...\r\n[OK]\r\nsfsw#"),
    ]


def test_install_cert_authenticates_ca_then_imports_leaf():
    chain = _chain(3)
    leaf, ca1, _ca2 = split_pem_certificates(chain)
    responses = _install_responses()
    chan = FakeChannel(responses)

    # The import confirmation only appears after the leaf's "quit"; make the second quit
    # produce the success line.
    quits = {"n": 0}
    original_send = chan.send

    def send(data: str) -> None:
        if data.strip() == "quit":
            quits["n"] += 1
            if quits["n"] == 2:
                chan.sent.append("quit")
                chan._pending += (
                    "\r\n% Router Certificate successfully imported\r\nsfsw(config)#"
                )
                return
        original_send(data)

    chan.send = send  # type: ignore[method-assign]

    plugin = CiscoIosDeployPlugin()
    plugin._open = lambda ctx: IosSession(chan, password="pw", paste_delay=0)  # type: ignore
    result = plugin.install_cert(
        _ctx({"trustpoint": "ACMELAN", "apply_to_https": True}, fullchain=chain)
    )
    assert result.ok, result.detail
    assert "trustpoint ACMELAN" in result.detail
    assert "not saved to startup-config" in result.detail  # write_memory defaults off

    sent = "\n".join(chan.sent)
    assert "crypto pki authenticate ACMELAN" in sent
    assert "crypto pki import ACMELAN certificate" in sent
    # The issuing CA (chain[1]) is what gets authenticated — not the leaf, not the root.
    assert ca1.strip().splitlines()[1] in sent
    assert leaf.strip().splitlines()[1] in sent
    assert "ip http secure-trustpoint ACMELAN" in sent
    assert "write memory" not in sent


def test_install_cert_writes_memory_only_when_enabled():
    chain = _chain(2)
    chan = FakeChannel(_install_responses())
    quits = {"n": 0}
    original_send = chan.send

    def send(data: str) -> None:
        if data.strip() == "quit":
            quits["n"] += 1
            if quits["n"] == 2:
                chan.sent.append("quit")
                chan._pending += "\r\n% Router Certificate successfully imported\r\nsfsw(config)#"
                return
        original_send(data)

    chan.send = send  # type: ignore[method-assign]
    plugin = CiscoIosDeployPlugin()
    plugin._open = lambda ctx: IosSession(chan, password="pw", paste_delay=0)  # type: ignore
    result = plugin.install_cert(
        _ctx({"trustpoint": "ACMELAN", "write_memory": True}, fullchain=chain)
    )
    assert result.ok, result.detail
    assert "configuration saved" in result.detail
    assert "write memory" in chan.sent


def test_install_cert_refuses_a_chain_without_a_ca():
    plugin = CiscoIosDeployPlugin()
    result = plugin.install_cert(_ctx({"trustpoint": "TP"}, fullchain=_chain(1)))
    assert not result.ok
    assert "no CA certificate" in result.detail


def test_install_cert_requires_a_trustpoint():
    plugin = CiscoIosDeployPlugin()
    result = plugin.install_cert(_ctx({}, fullchain=_chain(2)))
    assert not result.ok
    assert "trustpoint" in result.detail


# --- local mode (PKCS#12) ---


def test_build_pkcs12_wraps_base64_for_the_ios_terminal():
    """A single multi-kilobyte line is truncated by IOS ("BER decode failed")."""
    chain, key_pem = _chain_with_key(2)
    plugin = CiscoIosDeployPlugin()
    blob_b64 = plugin.build_pkcs12(
        _ctx({"trustpoint": "ACMELAN"}, fullchain=chain, key_pem=key_pem), "pw"
    )
    lines = blob_b64.splitlines()
    assert len(lines) > 1
    assert max(len(line) for line in lines) <= 64
    # Still decodes once the wrapping is removed.
    assert base64.b64decode("".join(lines))


def test_build_pkcs12_is_readable_with_the_transport_password():
    chain, key_pem = _chain_with_key(2)
    plugin = CiscoIosDeployPlugin()
    ctx = _ctx({"trustpoint": "ACMELAN"}, fullchain=chain, key_pem=key_pem)

    blob_b64 = plugin.build_pkcs12(ctx, "s3cret-transport")
    blob = base64.b64decode(blob_b64.replace("\n", ""))
    # The same password the IOS command is given must open the bundle.
    loaded_key, cert, cas = pkcs12.load_key_and_certificates(blob, b"s3cret-transport")
    assert loaded_key is not None
    assert cert.subject.rfc4514_string() == "CN=cert0"  # the leaf, not a CA
    assert len(cas) == 1
    with pytest.raises(ValueError):
        pkcs12.load_key_and_certificates(blob, b"wrong-password")


def test_deploy_imports_pkcs12_and_passes_matching_password():
    chain, key_pem = _chain_with_key(2)
    responses = [
        (r"terminal (length|width)", "\r\nsfsw#"),
        (r"configure terminal", "\r\nsfsw(config)#"),
        (
            r"crypto pki import .* pkcs12 terminal password",
            "\r\nEnter the base 64 encoded pkcs12.\r\n"
            "End with a blank line or the word \"quit\" on a line by itself",
        ),
        # A chain-bearing bundle makes IOS ask about the CAs above the leaf; the answer
        # must be yes so the device keeps the intermediates and can serve a full chain.
        (
            r"^quit$",
            "\r\n% Do you also want to create trustpoints for CAs higher in\r\n"
            "% the hierarchy? [yes/no]:",
        ),
        (r"^yes$", "\r\nCRYPTO_PKI: Imported PKCS12 file successfully.\r\nsfsw(config)#"),
        (r"ip http secure", "\r\nsfsw(config)#"),
        (r"^end$", "\r\nsfsw#"),
    ]
    chan = FakeChannel(responses)
    plugin = CiscoIosDeployPlugin()
    plugin._open = lambda ctx: IosSession(chan, password="pw", paste_delay=0)  # type: ignore
    result = plugin.deploy(
        _ctx({"trustpoint": "ACMELAN"}, fullchain=chain, key_pem=key_pem)
    )
    assert result.ok, result.detail
    assert "yes" in chan.sent, "the CA-hierarchy question must be answered"

    import_cmd = next(s for s in chan.sent if "pkcs12 terminal password" in s)
    password = import_cmd.rsplit("password ", 1)[1].strip()
    # Reassemble the base64 pasted between the import command and its terminating "quit",
    # and check it opens with exactly the password IOS was handed.
    start = chan.sent.index(import_cmd) + 1
    end = chan.sent.index("quit", start)
    blob = base64.b64decode("".join(chan.sent[start:end]))
    loaded_key, cert, _cas = pkcs12.load_key_and_certificates(blob, password.encode())
    assert loaded_key is not None and cert is not None


def test_deploy_without_a_key_fails_clearly():
    plugin = CiscoIosDeployPlugin()
    result = plugin.deploy(_ctx({"trustpoint": "TP"}, fullchain=_chain(2)))
    assert not result.ok
    assert "private key" in result.detail


# --- registration ---


def test_plugin_is_registered_with_its_fields():
    from acme_lan.deploy.factory import available_plugins, get_deploy_plugin, plugin_specs

    assert "cisco_ios" in available_plugins()
    plugin = get_deploy_plugin("cisco_ios")
    assert plugin.supports_csr_retrieval is True
    spec = next(s for s in plugin_specs() if s["name"] == "cisco_ios")
    keys = {f["key"] for f in spec["fields"]}
    assert {"trustpoint", "write_memory", "legacy_ssh", "apply_to_https"} <= keys
    write_memory = next(f for f in spec["fields"] if f["key"] == "write_memory")
    assert write_memory["type"] == "checkbox"
    # The default must be off: saving config is opt-in.
    assert "OFF by default" in write_memory["help"]


def test_install_cert_explains_a_chain_ios_cannot_anchor():
    """IOS anchors on a self-signed CA; public chains often ship none (e.g. Let's Encrypt)."""
    chain = _chain(2)
    responses = [
        (r"terminal (length|width)", "\r\nsfsw#"),
        (r"configure terminal", "\r\nsfsw(config)#"),
        (
            r"crypto pki authenticate",
            "\r\nEnter the base 64 encoded CA certificate.\r\n"
            "End with a blank line or the word \"quit\" on a line by itself",
        ),
        (r"^quit$", "\r\n% Error in saving certificate: status = FAIL\r\nsfsw(config)#"),
        (r"^end$", "\r\nsfsw#"),
    ]
    chan = FakeChannel(responses)
    plugin = CiscoIosDeployPlugin()
    plugin._open = lambda ctx: IosSession(chan, password="pw", paste_delay=0)  # type: ignore
    result = plugin.install_cert(_ctx({"trustpoint": "ACMELAN"}, fullchain=chain))
    assert not result.ok
    # The message has to point at a way out, not just echo the IOS error.
    assert "self-signed" in result.detail
    assert "'local' CSR mode" in result.detail
    assert "chain-validation continue" in result.detail


def test_paste_block_raises_on_ios_error_instead_of_swallowing_it():
    chan = FakeChannel(
        [(r"^quit$", "\r\n% Error in saving certificate: status = FAIL\r\nsfsw(config)#")]
    )
    session = IosSession(chan, password="pw", paste_delay=0)
    with pytest.raises(ShellError, match="Error in saving certificate"):
        session.paste_block("-----BEGIN CERTIFICATE-----\nAAA\n-----END CERTIFICATE-----")


def test_two_line_hierarchy_prompt_is_answered_exactly_once():
    """IOS wraps the question over two lines; answering twice leaves a bogus command."""
    chain, key_pem = _chain_with_key(3)
    responses = [
        (r"terminal (length|width)", "\r\nsfsw#"),
        (r"configure terminal", "\r\nsfsw(config)#"),
        (
            r"crypto pki import .* pkcs12 terminal password",
            "\r\nEnter the base 64 encoded pkcs12.\r\n"
            "End with a blank line or the word \"quit\" on a line by itself",
        ),
        (
            r"^quit$",
            "\r\n% The CA cert is not self-signed.\r\n"
            "% Do you also want to create trustpoints for CAs higher in\r\n"
            "% the hierarchy? [yes/no]:",
        ),
        (r"^yes$", "\r\nCRYPTO_PKI: Imported PKCS12 file successfully.\r\nsfsw(config)#"),
        (r"ip http secure", "\r\nsfsw(config)#"),
        (r"^end$", "\r\nsfsw#"),
    ]
    chan = FakeChannel(responses)
    plugin = CiscoIosDeployPlugin()
    plugin._open = lambda ctx: IosSession(chan, password="pw", paste_delay=0)  # type: ignore
    result = plugin.deploy(_ctx({"trustpoint": "TP"}, fullchain=chain, key_pem=key_pem))
    assert result.ok, result.detail
    assert chan.sent.count("yes") == 1, f"answered {chan.sent.count('yes')} times"

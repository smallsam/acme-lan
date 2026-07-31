"""SSH deploy plugin: install a cert over SFTP and run a reload command.

Supports both modes:
  - CSR-from-device (preferred): fetch a CSR from the device (via ``csr_command`` or
    ``remote_csr_path``), then ``install_cert`` uploads only the signed cert. The private
    key never leaves the device.
  - local key: ``deploy`` uploads both the cert and the acme-lan-generated key.

Authenticates with the host's stored credential (password or SSH private key). paramiko is
imported lazily so the rest of the app works even if it isn't installed.

Config keys:
  remote_cert_path  — path on the device for the fullchain PEM (required)
  remote_key_path   — path for the private key PEM (required for local-key mode)
  remote_csr_path   — path to read the device CSR from (CSR-from-device mode)
  csr_command       — command to run on the device that prints a CSR to stdout (alternative)
  reload_command    — optional command to run after install
  port              — SSH port (default 22)
"""

from __future__ import annotations

import io

from .base import DeployContext, DeployPlugin, DeployResult, PluginField


class SshDeployPlugin(DeployPlugin):
    name = "ssh"
    supports_csr_retrieval = True
    fields = [
        PluginField(
            "remote_cert_path", "Remote certificate path", required=True,
            modes=("device", "local"), placeholder="/etc/ssl/device.crt",
            help="Path on the device to upload the certificate chain to.",
        ),
        PluginField(
            "remote_key_path", "Remote key path", required=True, modes=("local",),
            placeholder="/etc/ssl/device.key", help="Path to upload the private key (local mode).",
        ),
        PluginField(
            "remote_csr_path", "Remote CSR path", modes=("device",),
            placeholder="/etc/ssl/device.csr",
            help="Read the device's CSR from this path (or use a CSR command).",
        ),
        PluginField(
            "csr_command", "CSR command", type="textarea", modes=("device",),
            placeholder="openssl req -new -key /etc/ssl/device.key -subj /CN=host ...",
            help="Command run on the device that prints a CSR to stdout (alternative to a path).",
        ),
        PluginField(
            "reload_command", "Reload command", modes=("device", "local"),
            placeholder="/etc/init.d/hostd restart",
            help="Optional command to run after installing.",
        ),
        PluginField(
            "port", "SSH port", type="number", modes=("device", "local"), placeholder="22",
        ),
    ]

    # --- connection helpers ---
    def _connect(self, ctx: DeployContext):
        import paramiko

        if ctx.credential is None:
            raise ValueError("ssh plugin requires a credential")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": ctx.host.address,
            "port": int(ctx.config.get("port", 22)),
            "username": ctx.credential.username,
            "timeout": 20,
        }
        if ctx.credential.kind == "ssh_key":
            kwargs["pkey"] = _load_pkey(paramiko, ctx.credential.secret)
        else:
            kwargs["password"] = ctx.credential.secret
        client.connect(**kwargs)
        return client

    @staticmethod
    def _paramiko():
        try:
            import paramiko

            return paramiko
        except ImportError:  # pragma: no cover
            return None

    # --- mode 1: CSR from device ---
    def fetch_csr(self, ctx: DeployContext) -> str:
        if self._paramiko() is None:
            raise RuntimeError("paramiko is not installed")
        client = self._connect(ctx)
        try:
            csr_command = ctx.config.get("csr_command")
            if csr_command:
                _stdin, stdout, stderr = client.exec_command(csr_command, timeout=60)
                rc = stdout.channel.recv_exit_status()
                out = stdout.read().decode()
                if rc != 0:
                    raise RuntimeError(f"csr_command failed ({rc}): {stderr.read().decode()}")
                return out
            remote_csr = ctx.config.get("remote_csr_path")
            if not remote_csr:
                raise ValueError(
                    "ssh CSR-from-device mode needs 'csr_command' or 'remote_csr_path'"
                )
            sftp = client.open_sftp()
            try:
                return _read(sftp, remote_csr)
            finally:
                sftp.close()
        finally:
            client.close()

    def install_cert(self, ctx: DeployContext) -> DeployResult:
        return self._upload(ctx, include_key=False)

    # --- mode 2: local key ---
    def deploy(self, ctx: DeployContext) -> DeployResult:
        return self._upload(ctx, include_key=True)

    def _upload(self, ctx: DeployContext, *, include_key: bool) -> DeployResult:
        if self._paramiko() is None:
            return DeployResult(False, "paramiko is not installed")
        cfg = ctx.config
        remote_cert = cfg.get("remote_cert_path")
        if not remote_cert:
            return DeployResult(False, "ssh plugin requires 'remote_cert_path'")
        if include_key and not cfg.get("remote_key_path"):
            return DeployResult(False, "ssh plugin requires 'remote_key_path' for local-key mode")
        try:
            client = self._connect(ctx)
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"ssh connect failed: {exc}")
        try:
            sftp = client.open_sftp()
            _write_remote(sftp, remote_cert, ctx.fullchain_pem, mode=0o644)
            if include_key and ctx.private_key_pem:
                _write_remote(sftp, cfg["remote_key_path"], ctx.private_key_pem, mode=0o600)
            sftp.close()

            reload_command = cfg.get("reload_command")
            if reload_command:
                _stdin, stdout, stderr = client.exec_command(reload_command, timeout=120)
                rc = stdout.channel.recv_exit_status()
                if rc != 0:
                    return DeployResult(
                        False, f"reload command failed ({rc}): {stderr.read().decode().strip()}"
                    )
            return DeployResult(True, f"uploaded to {ctx.host.address}:{remote_cert}")
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"ssh deploy failed: {exc}")
        finally:
            client.close()


def _read(sftp, path: str) -> str:
    with sftp.open(path, "r") as fh:
        data = fh.read()
    return data.decode() if isinstance(data, bytes) else data


def _load_pkey(paramiko, secret: str):
    for loader in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return loader.from_private_key(io.StringIO(secret))
        except Exception:  # noqa: BLE001
            continue
    raise ValueError("Could not parse SSH private key")


def _write_remote(sftp, path: str, content: str, mode: int) -> None:
    with sftp.open(path, "w") as fh:
        fh.write(content)
    sftp.chmod(path, mode)

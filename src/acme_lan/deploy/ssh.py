"""SSH deploy plugin: upload the cert + key over SFTP and run a reload command.

Authenticates with the host's stored credential — either a password or an SSH private key.
paramiko is imported lazily so the rest of the app works even if it isn't installed.

Config keys:
  remote_cert_path  — path on the device for the fullchain PEM (required)
  remote_key_path   — path on the device for the private key PEM (required)
  reload_command    — optional command to run after upload (e.g. restart the service)
  port              — SSH port (default 22)
"""

from __future__ import annotations

import io

from .base import DeployContext, DeployPlugin, DeployResult


class SshDeployPlugin(DeployPlugin):
    name = "ssh"

    def deploy(self, ctx: DeployContext) -> DeployResult:
        try:
            import paramiko
        except ImportError:  # pragma: no cover
            return DeployResult(False, "paramiko is not installed")

        cfg = ctx.config
        remote_cert = cfg.get("remote_cert_path")
        remote_key = cfg.get("remote_key_path")
        if not remote_cert or not remote_key:
            return DeployResult(
                False, "ssh plugin requires 'remote_cert_path' and 'remote_key_path'"
            )
        if ctx.credential is None:
            return DeployResult(False, "ssh plugin requires a credential")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connect_kwargs = {
            "hostname": ctx.host.address,
            "port": int(cfg.get("port", 22)),
            "username": ctx.credential.username,
            "timeout": 20,
        }
        if ctx.credential.kind == "ssh_key":
            connect_kwargs["pkey"] = _load_pkey(paramiko, ctx.credential.secret)
        else:
            connect_kwargs["password"] = ctx.credential.secret

        try:
            client.connect(**connect_kwargs)
            sftp = client.open_sftp()
            _write_remote(sftp, remote_cert, ctx.fullchain_pem, mode=0o644)
            _write_remote(sftp, remote_key, ctx.private_key_pem, mode=0o600)
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

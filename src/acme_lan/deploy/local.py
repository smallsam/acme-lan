"""Local filesystem deploy plugin.

Writes the certificate chain and key to configured paths and optionally runs a reload
command. Useful for services running on the same host as acme-lan, and as the reference
implementation of the plugin interface.

Config keys:
  cert_path       — where to write the fullchain PEM (required)
  key_path        — where to write the private key PEM (required)
  reload_command  — optional shell command to run after writing (e.g. "systemctl reload nginx")
"""

from __future__ import annotations

import os
import subprocess

from .base import DeployContext, DeployPlugin, DeployResult, PluginField


class LocalDeployPlugin(DeployPlugin):
    name = "local"
    supports_csr_retrieval = True
    fields = [
        PluginField(
            "cert_path", "Certificate path", required=True, modes=("device", "local"),
            placeholder="/etc/ssl/app.crt", help="Where to write the certificate chain (PEM).",
        ),
        PluginField(
            "key_path", "Private key path", required=True, modes=("local",),
            placeholder="/etc/ssl/app.key", help="Where to write the private key (local mode).",
        ),
        PluginField(
            "csr_path", "CSR path", required=True, modes=("device",),
            placeholder="/etc/ssl/app.csr",
            help="Read the device-generated CSR from here (device mode).",
        ),
        PluginField(
            "reload_command", "Reload command", modes=("device", "local"),
            placeholder="systemctl reload nginx", help="Optional command to run after writing.",
        ),
    ]

    def fetch_csr(self, ctx: DeployContext) -> str:
        """Read a CSR the local service generated itself (key never leaves the device)."""
        csr_path = ctx.config.get("csr_path")
        if not csr_path:
            raise ValueError("local plugin CSR-from-device mode requires 'csr_path' config")
        with open(csr_path) as fh:
            return fh.read()

    def install_cert(self, ctx: DeployContext) -> DeployResult:
        """Write only the certificate chain (no key) and optionally reload."""
        cert_path = ctx.config.get("cert_path")
        if not cert_path:
            return DeployResult(False, "local plugin requires 'cert_path' config")
        parent = os.path.dirname(cert_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(cert_path, "w") as fh:
            fh.write(ctx.fullchain_pem)
        return self._maybe_reload(ctx) or DeployResult(True, f"wrote {cert_path}")

    def _maybe_reload(self, ctx: DeployContext) -> DeployResult | None:
        reload_command = ctx.config.get("reload_command")
        if not reload_command:
            return None
        proc = subprocess.run(
            reload_command, shell=True, capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            return DeployResult(
                False, f"reload command failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return None

    def deploy(self, ctx: DeployContext) -> DeployResult:
        cert_path = ctx.config.get("cert_path")
        key_path = ctx.config.get("key_path")
        if not cert_path or not key_path:
            return DeployResult(False, "local plugin requires 'cert_path' and 'key_path' config")

        for path, content in ((cert_path, ctx.fullchain_pem), (key_path, ctx.private_key_pem)):
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w") as fh:
                fh.write(content)
        os.chmod(key_path, 0o600)

        reload_command = ctx.config.get("reload_command")
        if reload_command:
            proc = subprocess.run(
                reload_command, shell=True, capture_output=True, text=True, timeout=120
            )
            if proc.returncode != 0:
                return DeployResult(
                    False, f"reload command failed ({proc.returncode}): {proc.stderr.strip()}"
                )

        return DeployResult(True, f"wrote {cert_path} and {key_path}")

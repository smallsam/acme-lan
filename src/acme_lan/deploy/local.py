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

from .base import DeployContext, DeployPlugin, DeployResult


class LocalDeployPlugin(DeployPlugin):
    name = "local"

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

# Writing device-push plugins

acme-lan installs certificates onto devices that can't run an ACME client (ESXi, iDRAC/iLO,
switches, routers, printers, load balancers…) through **deploy plugins**. Most network gear
is driven over SSH/CLI, so an SSH-automation-style plugin is the common case and is covered
in detail below.

- [Two modes: device vs local](#two-modes-device-vs-local)
- [The plugin interface](#the-plugin-interface)
- [Registering a plugin](#registering-a-plugin)
- [Built-in plugins](#built-in-plugins)
- [Example: an SSH/CLI plugin for a network switch](#example-an-sshcli-plugin-for-a-network-switch)
- [Credentials](#credentials)
- [Testing a plugin](#testing-a-plugin)

---

## Two modes: device vs local

Each managed host has a `csr_source`:

- **`device` (preferred)** — acme-lan asks the *device* for a CSR, signs it, and pushes back
  only the certificate. **The private key never leaves the device.** Your plugin implements
  `fetch_csr()` and `install_cert()`.
- **`local`** — acme-lan generates the key + CSR itself and pushes **both**. Simpler for
  devices that can't produce a CSR, but acme-lan then holds the key (encrypted). Your plugin
  implements `deploy()`.

A plugin can support either or both. Set `supports_csr_retrieval = True` if it implements the
device flow (acme-lan rejects `csr_source=device` for plugins that don't).

## The plugin interface

Defined in [`src/acme_lan/deploy/base.py`](../src/acme_lan/deploy/base.py):

```python
@dataclass
class DeployContext:
    host: ManagedHost              # name, domains, address, port, config, ...
    fullchain_pem: str             # the issued certificate chain (PEM)
    private_key_pem: str | None    # the key — None in device mode (stays on the device)
    credential: DecryptedCredential | None   # kind ("password"|"ssh_key"), username, secret
    config: dict[str, Any]         # the host's plugin-specific config (free-form JSON)

@dataclass
class DeployResult:
    ok: bool
    detail: str = ""

class DeployPlugin(abc.ABC):
    name: str = "base"                 # unique registry name (what csr uses in the UI/API)
    supports_csr_retrieval: bool = False

    @abc.abstractmethod
    def deploy(self, ctx: DeployContext) -> DeployResult:
        """local mode: install the certificate AND private key."""

    def fetch_csr(self, ctx: DeployContext) -> str:
        """device mode, step 1: return a CSR (PEM) generated on the device."""
        raise NotImplementedError

    def install_cert(self, ctx: DeployContext) -> DeployResult:
        """device mode, step 2: install only the signed certificate (no key)."""
        raise NotImplementedError
```

Plugin methods are **synchronous** — acme-lan runs them in a worker thread, so blocking I/O
(SSH, HTTP, subprocess) is fine. Return a `DeployResult`; raising is also caught and recorded
on the host as `last_status`.

`config` is whatever JSON you put on the host (dashboard "Config (JSON)" field or the
`config` object in `POST /api/hosts`). Validate the keys your plugin needs and return
`DeployResult(False, "...")` if they're missing.

## Registering a plugin

```python
from acme_lan.deploy.factory import register_plugin
register_plugin(MyPlugin)          # keyed by MyPlugin.name
```

- **In-tree:** drop the class in `src/acme_lan/deploy/` and add it to the registry in
  [`deploy/factory.py`](../src/acme_lan/deploy/factory.py).
- **Out-of-tree:** call `register_plugin(MyPlugin)` at import time (e.g. from a small startup
  module). It then appears in `GET /api/deploy-plugins` and is selectable per host.

## Built-in plugins

| Plugin | Modes | Key config |
| --- | --- | --- |
| [`local`](../src/acme_lan/deploy/local.py) | device, local | `cert_path`, `key_path` (local mode), `reload_command`, `csr_path` (device mode) |
| [`ssh`](../src/acme_lan/deploy/ssh.py) | device, local | `remote_cert_path`, `remote_key_path` (local mode), `remote_csr_path` **or** `csr_command` (device mode), `reload_command`, `port` |

Example host config for the built-in `ssh` plugin in **device** mode (key stays on the box):

```json
{
  "csr_command": "openssl req -new -key /etc/ssl/device.key -subj /CN=esxi01.lan.test -addext subjectAltName=DNS:esxi01.lan.test",
  "remote_cert_path": "/etc/vmware/ssl/rui.crt",
  "reload_command": "/etc/init.d/hostd restart"
}
```

## Example: an SSH/CLI plugin for a network switch

Many switches/routers accept a cert over an interactive CLI rather than a plain file copy.
This plugin (device mode) runs the vendor CLI over SSH: it asks the device to emit a CSR,
then pastes the signed certificate back and applies it. Adapt the commands to your vendor.

```python
# my_plugins/switch.py
from __future__ import annotations

from acme_lan.deploy.base import DeployContext, DeployPlugin, DeployResult
from acme_lan.deploy.factory import register_plugin


class SwitchCliPlugin(DeployPlugin):
    name = "switch-cli"
    supports_csr_retrieval = True          # implements the preferred device flow

    def _connect(self, ctx: DeployContext):
        import paramiko

        if ctx.credential is None:
            raise ValueError("switch-cli requires a credential")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": ctx.host.address,
            "port": int(ctx.config.get("port", 22)),
            "username": ctx.credential.username,
            "timeout": 20,
        }
        if ctx.credential.kind == "ssh_key":
            kwargs["pkey"] = paramiko.RSAKey.from_private_key(
                __import__("io").StringIO(ctx.credential.secret)
            )
        else:
            kwargs["password"] = ctx.credential.secret
        client.connect(**kwargs)
        return client

    def _run(self, client, command: str) -> str:
        _stdin, stdout, stderr = client.exec_command(command, timeout=60)
        rc = stdout.channel.recv_exit_status()
        out = stdout.read().decode()
        if rc != 0:
            raise RuntimeError(f"{command!r} failed ({rc}): {stderr.read().decode()}")
        return out

    # device mode, step 1 — have the switch generate a keypair + CSR and print the CSR
    def fetch_csr(self, ctx: DeployContext) -> str:
        domain = ctx.host.domains[0]
        client = self._connect(ctx)
        try:
            gen = ctx.config.get(
                "csr_command",
                # generic OpenSSL example; replace with your vendor's CLI
                f"openssl req -new -newkey rsa:2048 -nodes "
                f"-keyout /flash/acme.key -subj /CN={domain} "
                f"-addext subjectAltName=DNS:{domain}",
            )
            return self._run(client, gen)          # CSR PEM on stdout
        finally:
            client.close()

    # device mode, step 2 — install only the signed certificate
    def install_cert(self, ctx: DeployContext) -> DeployResult:
        remote = ctx.config.get("remote_cert_path", "/flash/acme.crt")
        client = self._connect(ctx)
        try:
            sftp = client.open_sftp()
            with sftp.open(remote, "w") as fh:
                fh.write(ctx.fullchain_pem)
            sftp.close()
            reload_cmd = ctx.config.get("reload_command")
            if reload_cmd:
                self._run(client, reload_cmd)      # e.g. apply/commit the new cert
            return DeployResult(True, f"installed cert on {ctx.host.address}:{remote}")
        except Exception as exc:  # noqa: BLE001
            return DeployResult(False, f"switch-cli deploy failed: {exc}")
        finally:
            client.close()


register_plugin(SwitchCliPlugin)
```

A host using it:

```json
{
  "name": "switch-core",
  "domains": ["switch.lan.test"],
  "address": "192.168.3.1",
  "deploy_plugin": "switch-cli",
  "csr_source": "device",
  "credential_id": "<id of an ssh_key or password credential>",
  "config": { "remote_cert_path": "/flash/acme.crt", "reload_command": "copy running-config startup-config" }
}
```

For a **local-mode** device (acme-lan generates the key), implement `deploy()` instead —
upload both `ctx.fullchain_pem` and `ctx.private_key_pem`, then reload. See the built-in
[`ssh`](../src/acme_lan/deploy/ssh.py) plugin for a complete both-modes reference.

## Credentials

`ctx.credential` is resolved from the host's `credential_id` at deploy time:

- `kind` is `"password"` or `"ssh_key"`; `username` and `secret` carry the value.
- The secret may be stored locally (Fernet-encrypted) or fetched from **Azure Key Vault** /
  **HashiCorp Vault** — your plugin just receives the decrypted value and never deals with
  storage. Create credentials via `POST /api/credentials` (see the deployment guide).

## Testing a plugin

Register it and drive `renew_and_deploy` with a fake issuer so no CA is needed:

```python
from acme_lan.deploy.factory import register_plugin
from acme_lan.hosts import renew_and_deploy
# register_plugin(SwitchCliPlugin)  # (or import the module that does)

cert, result = await renew_and_deploy(host, session, issuer=lambda csr_pem: SOME_TEST_CHAIN_PEM)
assert result.ok
```

See [`tests/test_device_csr_mode.py`](../tests/test_device_csr_mode.py) for a worked example
of a fake device-mode plugin, and [`tests/test_deploy_local.py`](../tests/test_deploy_local.py)
for the local-mode plugin tests.

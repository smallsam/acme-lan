"""Interactive shell transports for network devices that need a real CLI session.

Appliances like Cisco IOS don't accept SSH "exec" commands (no ``exec_command``) and drive
everything through an interactive terminal with prompts, so this module provides a small
send/expect channel with two backends:

* **paramiko** — pure Python, used for anything that speaks modern SSH.
* **openssh** — the system ``ssh`` binary on a pty, needed for legacy gear. paramiko 5
  removed ``ssh-rsa``, ``diffie-hellman-group1-sha1`` and ``diffie-hellman-group14-sha1``
  outright (the implementations are gone, not merely deprioritised), so older IOS boxes
  that offer nothing else are unreachable with it. OpenSSH still supports them when they
  are explicitly re-enabled per connection.

The send/expect API is deliberately tiny (``send`` / ``expect`` / ``close``) so device
logic can be written against it and unit-tested with a scripted fake channel.
"""

from __future__ import annotations

import abc
import fcntl
import os
import pty
import re
import select
import shutil
import subprocess
import termios
import time

# Legacy algorithms, as an OpenSSH would-be ssh_config. Appended with "+" so the modern
# defaults stay available and one option set works across a mixed fleet.
LEGACY_SSH_OPTIONS: tuple[str, ...] = (
    "-o", "KexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group-exchange-sha1,"
    "diffie-hellman-group1-sha1",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
    "-o", "Ciphers=+aes256-cbc,aes128-cbc,3des-cbc",
    "-o", "MACs=+hmac-sha1",
)


class ShellError(RuntimeError):
    pass


class ShellTimeout(ShellError):
    pass


class Channel(abc.ABC):
    """A bidirectional interactive session."""

    @abc.abstractmethod
    def send(self, data: str) -> None: ...

    @abc.abstractmethod
    def read(self, timeout: float) -> str:
        """Read whatever is available within ``timeout``; '' if nothing arrived."""

    @abc.abstractmethod
    def close(self) -> None: ...

    def expect(self, pattern: str, timeout: float = 30.0) -> str:
        """Accumulate output until ``pattern`` matches; return everything read."""
        rx = re.compile(pattern)
        buf = ""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            buf += self.read(min(0.5, max(0.05, deadline - time.monotonic())))
            if rx.search(buf):
                return buf
        raise ShellTimeout(f"timed out waiting for {pattern!r}; last output:\n{buf[-1500:]}")


class ParamikoChannel(Channel):
    """Interactive shell over paramiko's ``invoke_shell``."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        *,
        password: str | None = None,
        pkey_pem: str | None = None,
        timeout: float = 25.0,
    ) -> None:
        try:
            import paramiko
        except ImportError as exc:  # pragma: no cover
            raise ShellError("paramiko is not installed") from exc

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": timeout,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if pkey_pem:
            import io

            for loader in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
                try:
                    kwargs["pkey"] = loader.from_private_key(io.StringIO(pkey_pem))
                    break
                except Exception:  # noqa: BLE001
                    continue
            else:
                raise ShellError("Could not parse the SSH private key")
        else:
            kwargs["password"] = password
        client.connect(**kwargs)
        self._client = client
        self._chan = client.invoke_shell(width=200, height=1000)
        self._chan.settimeout(0.0)

    def send(self, data: str) -> None:
        self._chan.sendall(data.encode())

    def read(self, timeout: float) -> str:
        end = time.monotonic() + timeout
        out = ""
        while time.monotonic() < end:
            if self._chan.recv_ready():
                out += self._chan.recv(65536).decode("utf-8", "replace")
                break
            time.sleep(0.05)
        return out

    def close(self) -> None:
        try:
            self._chan.close()
        finally:
            self._client.close()


class OpenSshPtyChannel(Channel):
    """Interactive shell over the system ``ssh`` binary attached to a pty.

    A pty is required for two reasons: OpenSSH will only prompt for a password on a
    controlling terminal (otherwise it reaches for ``ssh-askpass``), and IOS needs a
    terminal to run its interactive CLI at all.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        *,
        password: str | None = None,
        pkey_pem: str | None = None,
        legacy: bool = False,
        extra_options: tuple[str, ...] = (),
        timeout: float = 25.0,
    ) -> None:
        ssh = shutil.which("ssh")
        if not ssh:
            raise ShellError(
                "the openssh transport needs the 'ssh' binary (install openssh-client)"
            )
        args = [
            ssh,
            "-tt",  # force a pty on the remote side even though our stdin is a pty
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", f"ConnectTimeout={int(timeout)}",
            "-o", "NumberOfPasswordPrompts=1",
            "-p", str(port),
        ]
        if legacy:
            args += list(LEGACY_SSH_OPTIONS)
        pass_fds: tuple[int, ...] = ()
        key_fd = None
        if pkey_pem:
            # Hand the key to ssh through an in-memory fd so no plaintext key is written to
            # disk (same approach as the service-certificate key in selfcert.py).
            key_fd = os.memfd_create("acme-lan-ssh-key")
            os.write(key_fd, pkey_pem.encode())
            os.lseek(key_fd, 0, 0)
            os.set_inheritable(key_fd, True)
            pass_fds = (key_fd,)
            args += [
                "-o", "IdentitiesOnly=yes",
                "-o", "PreferredAuthentications=publickey",
                "-i", f"/proc/self/fd/{key_fd}",
            ]
        elif password is not None:
            args += ["-o", "PreferredAuthentications=keyboard-interactive,password"]
        args += list(extra_options)
        args.append(f"{username}@{host}")

        def _preexec() -> None:
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        # DISPLAY/SSH_ASKPASS would divert the password prompt away from our pty.
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("DISPLAY", "SSH_ASKPASS", "SSH_ASKPASS_REQUIRE")
        }
        master, slave = pty.openpty()
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
                args,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                preexec_fn=_preexec,  # noqa: PLW1509
                env=env,
                close_fds=True,
                pass_fds=pass_fds,
            )
        finally:
            os.close(slave)
            if key_fd is not None:
                os.close(key_fd)
        self._fd = master

    def send(self, data: str) -> None:
        os.write(self._fd, data.encode())

    def read(self, timeout: float) -> str:
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return ""
        try:
            return os.read(self._fd, 65536).decode("utf-8", "replace")
        except OSError:  # pty closed when the child exited
            return ""

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            self._proc.kill()

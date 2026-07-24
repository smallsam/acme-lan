"""Edge HTTP-01 responder.

Serves ``/.well-known/acme-challenge/<token>`` so the upstream CA can validate an
http-01 challenge by connecting to this server on the network edge. This is the
alternative to DNS-01 for identifiers that *are* publicly reachable (e.g. wildcard DNS
points at the edge IP), and is typically faster than DNS propagation.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_CHALLENGE_PREFIX = "/.well-known/acme-challenge/"


class EdgeHttpResponder:
    def __init__(self, port: int, bind: str = "0.0.0.0") -> None:  # noqa: S104
        self._tokens: dict[str, str] = {}
        self.port = port
        responder = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if not self.path.startswith(_CHALLENGE_PREFIX):
                    self.send_response(404)
                    self.end_headers()
                    return
                token = self.path[len(_CHALLENGE_PREFIX) :]
                content = responder._tokens.get(token)
                if content is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = content.encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):  # silence
                pass

        self._server = ThreadingHTTPServer((bind, port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def register(self, token: str, key_authorization: str) -> None:
        self._tokens[token] = key_authorization

    def unregister(self, token: str) -> None:
        self._tokens.pop(token, None)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

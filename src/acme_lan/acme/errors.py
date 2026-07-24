"""RFC 8555 problem documents (application/problem+json)."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

ACME_ERROR_NS = "urn:ietf:params:acme:error:"


class AcmeError(Exception):
    """An ACME protocol error rendered as a problem+json document."""

    def __init__(
        self,
        error_type: str,
        detail: str,
        status: int = 400,
        subproblems: list[dict[str, Any]] | None = None,
    ) -> None:
        # Accept either a bare token ("malformed") or a full URN.
        self.type = error_type if error_type.startswith("urn:") else ACME_ERROR_NS + error_type
        self.detail = detail
        self.status = status
        self.subproblems = subproblems
        super().__init__(detail)

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"type": self.type, "detail": self.detail, "status": self.status}
        if self.subproblems:
            doc["subproblems"] = self.subproblems
        return doc


# Convenience constructors for the errors we raise most.
def malformed(detail: str) -> AcmeError:
    return AcmeError("malformed", detail, status=400)


def unauthorized(detail: str) -> AcmeError:
    return AcmeError("unauthorized", detail, status=401)


def account_does_not_exist(detail: str = "Account does not exist") -> AcmeError:
    return AcmeError("accountDoesNotExist", detail, status=400)


def bad_nonce(detail: str = "Invalid or reused anti-replay nonce") -> AcmeError:
    return AcmeError("badNonce", detail, status=400)


def unsupported_identifier(detail: str) -> AcmeError:
    return AcmeError("unsupportedIdentifier", detail, status=400)


def server_internal(detail: str) -> AcmeError:
    return AcmeError("serverInternal", detail, status=500)


def order_not_ready(detail: str = "Order is not in the ready state") -> AcmeError:
    return AcmeError("orderNotReady", detail, status=403)


def problem_response(err: AcmeError, extra_headers: dict[str, str] | None = None) -> JSONResponse:
    headers = {"Content-Type": "application/problem+json"}
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(status_code=err.status, content=err.to_dict(), headers=headers)


async def acme_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """FastAPI exception handler that renders :class:`AcmeError` and adds a fresh nonce."""
    from .nonce import issue_nonce

    assert isinstance(exc, AcmeError)
    nonce = await issue_nonce()
    return problem_response(exc, extra_headers={"Replay-Nonce": nonce})

"""Correlate a live TLS probe with the certificates acme-lan has issued.

``health.probe_tls`` answers "what is this endpoint serving, is the chain trusted, has it
expired". This module answers a different question: *is the endpoint serving the
certificate we issued, and is whoever renews it keeping up?* The two are reported
separately, so a trusted-and-unexpired endpoint that is quietly serving a year-old
certificate (or one from another CA entirely) still shows up as a problem.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass
class IssuedCert:
    """A certificate acme-lan has issued, as far as the audit is concerned."""

    serial: str | None = None
    not_after: datetime | None = None
    issued_at: datetime | None = None
    issuer: str | None = None
    retired: bool = False


@dataclass
class Finding:
    code: str
    severity: str  # "info" | "warning" | "error"
    message: str


@dataclass
class DeploymentAudit:
    # ok        — serving the newest certificate we issued
    # stale     — serving one of ours, but not the newest
    # foreign   — serving a certificate from a CA we have never issued from
    # unknown   — serial we have no record of (same CA, so likely another client)
    # unknown_records — we hold no certificates for this name, nothing to compare
    status: str = "unknown_records"
    matches_issued: bool | None = None
    matches_latest: bool | None = None
    # Whether the endpoint is serving *this particular* certificate. The rest of the audit
    # describes the endpoint (shared by every certificate issued for the name), so this is
    # what distinguishes the live row from superseded ones in a list.
    serving_this: bool | None = None
    latest_issued_serial: str | None = None
    latest_issued_at: str | None = None
    latest_issued_not_after: str | None = None
    renewal_overdue: bool | None = None
    renewal_due_at: str | None = None
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _norm_serial(serial: str | None) -> str | None:
    """Normalise a hex serial for comparison (case, 0x prefix, leading zeros)."""
    if not serial:
        return None
    text = serial.strip().lower().replace(":", "").removeprefix("0x").lstrip("0")
    return text or "0"


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat those as UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _sort_key(cert: IssuedCert) -> datetime:
    return (
        _aware(cert.not_after)
        or _aware(cert.issued_at)
        or datetime.min.replace(tzinfo=UTC)
    )


def audit_deployment(
    *,
    served_serial: str | None,
    served_issuer: str | None,
    issued: list[IssuedCert],
    renew_before_days: int,
    this_serial: str | None = None,
    now: datetime | None = None,
) -> DeploymentAudit:
    """Compare a served certificate against what acme-lan issued for the same name.

    ``renew_before_days`` is the point at which a compliant ACME client is expected to
    have renewed (clients typically renew at a third of the lifetime remaining), so a
    newest-issued certificate past that point means nobody has come back for a renewal.
    """
    now = now or datetime.now(UTC)
    audit = DeploymentAudit()
    if this_serial and served_serial:
        audit.serving_this = _norm_serial(this_serial) == _norm_serial(served_serial)
    # Retired certificates are deliberately out of service; they must not count as "latest".
    live = [c for c in issued if not c.retired]
    if not live:
        audit.findings.append(
            Finding(
                "no_issued_certificates",
                "info",
                "acme-lan has not issued a certificate for this name, so the served "
                "certificate cannot be compared against its own records.",
            )
        )
        return audit

    latest = max(live, key=_sort_key)
    served = _norm_serial(served_serial)
    known = {s for s in (_norm_serial(c.serial) for c in live) if s}
    known_issuers = {c.issuer for c in live if c.issuer}

    audit.latest_issued_serial = latest.serial
    audit.latest_issued_at = (
        _aware(latest.issued_at).isoformat() if latest.issued_at else None
    )
    audit.latest_issued_not_after = (
        _aware(latest.not_after).isoformat() if latest.not_after else None
    )
    audit.matches_issued = served in known if served else None
    audit.matches_latest = (
        served == _norm_serial(latest.serial) if served and latest.serial else None
    )

    if audit.matches_latest:
        audit.status = "ok"
    elif audit.matches_issued:
        audit.status = "stale"
        issued_on = audit.latest_issued_at[:10] if audit.latest_issued_at else "unknown date"
        audit.findings.append(
            Finding(
                "not_latest_certificate",
                "warning",
                f"Serving an older certificate: a newer one (serial "
                f"{latest.serial}, issued {issued_on}) has been issued but is not "
                "installed on the endpoint.",
            )
        )
    elif served is None:
        audit.status = "unknown_records"
    elif served_issuer and served_issuer not in known_issuers:
        audit.status = "foreign"
        audit.findings.append(
            Finding(
                "third_party_issuer",
                "warning",
                f"The served certificate was issued by {served_issuer}, which is not a CA "
                "acme-lan has issued this name from — it was obtained outside acme-lan.",
            )
        )
    else:
        audit.status = "unknown"
        audit.findings.append(
            Finding(
                "unknown_certificate",
                "warning",
                f"The served certificate (serial {served_serial}) was not issued through "
                "acme-lan, though it comes from a CA acme-lan also uses.",
            )
        )

    # Renewal timeliness is judged on the newest certificate we hold: if the device is
    # merely behind (status "stale") the client did renew, so this stays clean.
    reference = _aware(latest.not_after)
    if reference is not None:
        due_at = reference - timedelta(days=renew_before_days)
        audit.renewal_due_at = due_at.isoformat()
        audit.renewal_overdue = now > due_at
        if audit.renewal_overdue:
            days_left = (reference - now).days
            expired = now > reference
            audit.findings.append(
                Finding(
                    "renewal_overdue",
                    "error" if expired else "warning",
                    (
                        f"The newest certificate acme-lan issued for this name expired "
                        f"{abs(days_left)} day(s) ago and no renewal has been requested."
                        if expired
                        else f"No renewal has been requested and the newest certificate "
                        f"acme-lan issued expires in {days_left} day(s); a compliant ACME "
                        f"client renews with at least {renew_before_days} days remaining."
                    ),
                )
            )
    return audit

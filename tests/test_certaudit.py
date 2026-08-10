"""Unit tests for correlating a served certificate with what acme-lan issued."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from acme_lan.certaudit import IssuedCert, audit_deployment

NOW = datetime(2026, 8, 6, tzinfo=UTC)
LE = "CN=YR1,O=Let's Encrypt,C=US"


def _codes(audit) -> set[str]:
    return {f.code for f in audit.findings}


def test_serving_latest_issued_is_ok():
    audit = audit_deployment(
        served_serial="ABCD",
        served_issuer=LE,
        issued=[
            IssuedCert("abcd", NOW + timedelta(days=80), NOW - timedelta(days=10), LE),
            IssuedCert("00ff", NOW + timedelta(days=5), NOW - timedelta(days=85), LE),
        ],
        renew_before_days=30,
        now=NOW,
    )
    assert audit.status == "ok"
    assert audit.matches_issued is True and audit.matches_latest is True
    # Serial comparison is case- and leading-zero-insensitive.
    assert audit.renewal_overdue is False
    assert audit.findings == []


def test_stale_deployment_flags_newer_certificate_without_renewal_warning():
    audit = audit_deployment(
        served_serial="00ff",
        served_issuer=LE,
        issued=[
            IssuedCert("abcd", NOW + timedelta(days=80), NOW - timedelta(days=10), LE),
            IssuedCert("ff", NOW + timedelta(days=5), NOW - timedelta(days=85), LE),
        ],
        renew_before_days=30,
        now=NOW,
    )
    assert audit.status == "stale"
    assert audit.matches_issued is True and audit.matches_latest is False
    # The client *did* renew (a newer cert exists), so renewal is not overdue.
    assert _codes(audit) == {"not_latest_certificate"}
    assert audit.renewal_overdue is False


def test_third_party_issuer_is_reported():
    audit = audit_deployment(
        served_serial="9999",
        served_issuer="CN=DigiCert TLS RSA,O=DigiCert",
        issued=[IssuedCert("abcd", NOW + timedelta(days=80), NOW, LE)],
        renew_before_days=30,
        now=NOW,
    )
    assert audit.status == "foreign"
    assert _codes(audit) == {"third_party_issuer"}
    assert "DigiCert" in audit.findings[0].message


def test_unknown_serial_from_same_ca_is_distinguished_from_third_party():
    audit = audit_deployment(
        served_serial="9999",
        served_issuer=LE,
        issued=[IssuedCert("abcd", NOW + timedelta(days=80), NOW, LE)],
        renew_before_days=30,
        now=NOW,
    )
    assert audit.status == "unknown"
    assert _codes(audit) == {"unknown_certificate"}


def test_renewal_overdue_when_newest_issued_is_inside_the_window():
    audit = audit_deployment(
        served_serial="abcd",
        served_issuer=LE,
        issued=[IssuedCert("abcd", NOW + timedelta(days=10), NOW - timedelta(days=80), LE)],
        renew_before_days=30,
        now=NOW,
    )
    assert audit.status == "ok"  # deployment matches; the problem is renewal timeliness
    assert audit.renewal_overdue is True
    assert _codes(audit) == {"renewal_overdue"}
    finding = audit.findings[0]
    assert finding.severity == "warning" and "10 day" in finding.message


def test_expired_newest_issued_escalates_to_error():
    audit = audit_deployment(
        served_serial="abcd",
        served_issuer=LE,
        issued=[IssuedCert("abcd", NOW - timedelta(days=3), NOW - timedelta(days=93), LE)],
        renew_before_days=30,
        now=NOW,
    )
    assert audit.renewal_overdue is True
    assert audit.findings[0].severity == "error"
    assert "3 day(s) ago" in audit.findings[0].message


def test_retired_certificates_are_not_treated_as_latest():
    audit = audit_deployment(
        served_serial="abcd",
        served_issuer=LE,
        issued=[
            IssuedCert("abcd", NOW + timedelta(days=80), NOW, LE),
            IssuedCert("dead", NOW + timedelta(days=90), NOW, LE, retired=True),
        ],
        renew_before_days=30,
        now=NOW,
    )
    assert audit.status == "ok"
    assert audit.latest_issued_serial == "abcd"


def test_no_issued_records_reports_info_only():
    audit = audit_deployment(
        served_serial="abcd", served_issuer=LE, issued=[], renew_before_days=30, now=NOW
    )
    assert audit.status == "unknown_records"
    assert _codes(audit) == {"no_issued_certificates"}
    assert audit.findings[0].severity == "info"


def test_serving_this_distinguishes_the_live_certificate_from_superseded_rows():
    """The audit describes the endpoint; serving_this marks which row is actually deployed."""
    issued = [
        IssuedCert("abcd", NOW + timedelta(days=80), NOW - timedelta(days=10), LE),
        IssuedCert("00ff", NOW + timedelta(days=5), NOW - timedelta(days=85), LE),
    ]
    live = audit_deployment(
        served_serial="abcd", served_issuer=LE, issued=issued,
        renew_before_days=30, this_serial="ABCD", now=NOW,
    )
    old = audit_deployment(
        served_serial="abcd", served_issuer=LE, issued=issued,
        renew_before_days=30, this_serial="ff", now=NOW,
    )
    assert live.serving_this is True
    assert old.serving_this is False
    # Both describe the same (healthy) endpoint.
    assert live.status == old.status == "ok"
    assert live.findings == old.findings == []


def test_serving_this_is_unknown_without_a_serial_to_compare():
    audit = audit_deployment(
        served_serial=None, served_issuer=None,
        issued=[IssuedCert("abcd", NOW + timedelta(days=80), NOW, LE)],
        renew_before_days=30, now=NOW,
    )
    assert audit.serving_this is None

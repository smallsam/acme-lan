"""Remote secret providers (mirrors the certificate storage backends).

Used to fetch device-push credentials that live in an external secret manager rather than
the local (encrypted) database, so credentials need never be copied into acme-lan.
"""

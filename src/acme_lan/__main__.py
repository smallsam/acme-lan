"""Console entrypoint: ``acme-lan`` runs the server with uvicorn."""

from __future__ import annotations

import logging

import uvicorn

from .config import get_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    host = "0.0.0.0"  # noqa: S104 - a LAN service is meant to listen broadly
    port = 8000
    # If external_url encodes a localhost port, honour it for local runs.
    if settings.external_url.startswith("http://localhost:"):
        port = int(settings.external_url.rsplit(":", 1)[1].split("/")[0])
    uvicorn.run("acme_lan.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

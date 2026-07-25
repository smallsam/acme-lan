#!/usr/bin/env bash
# Devcontainer bootstrap: install all Python + frontend dev dependencies and the
# Pebble test binaries so the full test suite (incl. e2e) runs out of the box.
set -euo pipefail

echo "== Installing uv =="
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "== Installing Python deps (runtime + dev + storage extras) =="
uv sync --extra dev --extra storage

echo "== Building the Vue dashboard =="
( cd src/acme_lan/web && npm install && npm run build )

echo "== Building Pebble + challtestsrv for e2e tests =="
export GOBIN="${GOBIN:-$HOME/go/bin}"
go install github.com/letsencrypt/pebble/v2/cmd/pebble@latest
go install github.com/letsencrypt/pebble/v2/cmd/pebble-challtestsrv@latest

echo "== Done. Run: uv run pytest -q =="

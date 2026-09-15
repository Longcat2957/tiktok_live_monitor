#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"
# Fetch/review source changes separately; do not overwrite a local checkout.
docker compose build
docker compose up -d --wait --wait-timeout 120

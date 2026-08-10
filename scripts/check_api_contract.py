#!/usr/bin/env python3
"""Check or regenerate the frontend workflow status contract from OpenAPI."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "process-plan-agent-api"
GENERATED_CONTRACT = REPO_ROOT / "process-plan-agent-ui" / "src" / "api" / "generated" / "status.ts"
sys.path.insert(0, str(API_ROOT))

from app.contracts.openapi import render_frontend_status_contract, validate_openapi_contract  # noqa: E402
from app.main import app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the frontend status contract")
    args = parser.parse_args()

    openapi = app.openapi()
    errors = validate_openapi_contract(openapi)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    expected = render_frontend_status_contract(openapi)
    if args.write:
        GENERATED_CONTRACT.parent.mkdir(parents=True, exist_ok=True)
        GENERATED_CONTRACT.write_text(expected, encoding="utf-8")
        print(f"Updated {GENERATED_CONTRACT.relative_to(REPO_ROOT)}")
        return 0

    actual = GENERATED_CONTRACT.read_text(encoding="utf-8") if GENERATED_CONTRACT.exists() else ""
    if actual != expected:
        print(
            "ERROR: frontend status contract is stale; run "
            "node scripts/check_api_contract.mjs --write",
            file=sys.stderr,
        )
        return 1

    print("API contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

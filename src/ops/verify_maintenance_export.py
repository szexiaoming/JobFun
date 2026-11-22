"""Verify a maintenance export checksum and safe schema without a database."""

from __future__ import annotations

import argparse
import sys

import config
from src.ops.maintenance_export_integrity import (
    load_document,
    parse_hmac_keyring,
    verify_document,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Maintenance export JSON file to verify.")
    parser.add_argument(
        "--require-authentication",
        action="store_true",
        help="Reject checksum-only exports that do not contain HMAC authentication.",
    )
    args = parser.parse_args(argv)
    try:
        document = load_document(args.path)
        keyring = parse_hmac_keyring(config.MAINTENANCE_EXPORT_HMAC_KEYS_JSON)
    except (OSError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    report = verify_document(
        document,
        authentication_keys=keyring,
        require_authentication=args.require_authentication,
    )
    if not report.valid:
        for error in report.errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print(
        "VALID: maintenance export integrity and schema verified "
        f"({report.run_count} run records)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

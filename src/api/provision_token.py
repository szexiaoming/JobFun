"""Local CLI for issuing a revocable API token to an existing user."""

from __future__ import annotations

import argparse
from datetime import timedelta

from src.db.sqlite_client import Database
from src.repositories.sqlite_auth import SQLiteAuthRepository
from src.services.authentication import AuthenticationService


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Issue one JobFun API bearer token. The raw token is shown once.",
    )
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--label", default="local-api")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    if args.user_id <= 0 or args.days <= 0:
        parser.error("--user-id and --days must be positive")

    with Database() as database:
        service = AuthenticationService(SQLiteAuthRepository(database))
        issued = service.issue_token(
            user_id=args.user_id,
            label=args.label,
            lifetime=timedelta(days=args.days),
        )
    if issued is None:
        print("Token not created: user does not exist or is inactive.")
        return 1
    print("Store this token securely; it will not be shown again:")
    print(issued.token)
    print(f"Expires at: {issued.expires_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

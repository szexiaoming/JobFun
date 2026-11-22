"""SQLite authentication adapter."""

from __future__ import annotations

import json

from src.db.models import ApiToken
from src.db.sqlite_client import Database
from src.repositories.contracts import AuthPrincipal


class SQLiteAuthRepository:
    def __init__(self, database: Database):
        self._database = database

    def find_principal_by_token_hash(
        self,
        token_hash: str,
        now: str,
    ) -> AuthPrincipal | None:
        row = self._database.fetch_one(
            """
            SELECT u.id, u.username, u.settings_json
            FROM api_tokens AS token
            JOIN users AS u ON u.id = token.user_id
            WHERE token.token_hash = ?
              AND token.revoked_at = ''
              AND token.expires_at > ?
              AND u.is_active = 1
            LIMIT 1
            """,
            (token_hash, now),
        )
        if not row:
            return None
        roles = _roles_from_settings(row.get("settings_json"))
        return AuthPrincipal(
            user_id=int(row["id"]),
            username=str(row["username"]),
            roles=roles,
        )

    def touch_token(self, token_hash: str, used_at: str) -> None:
        self._database.execute(
            "UPDATE api_tokens SET last_used_at = ? WHERE token_hash = ?",
            (used_at, token_hash),
        )

    def create_token(
        self,
        *,
        user_id: int,
        token_hash: str,
        label: str,
        expires_at: str,
        created_at: str,
    ) -> int | None:
        owner = self._database.fetch_one(
            "SELECT id FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        )
        if not owner:
            return None
        return self._database.insert(
            "api_tokens",
            ApiToken(
                user_id=user_id,
                token_hash=token_hash,
                label=label,
                expires_at=expires_at,
                created_at=created_at,
            ),
        )

    def revoke_token(self, *, user_id: int, token_id: int, revoked_at: str) -> bool:
        changed = self._database.execute(
            """
            UPDATE api_tokens
            SET revoked_at = ?
            WHERE id = ? AND user_id = ? AND revoked_at = ''
            """,
            (revoked_at, token_id, user_id),
        )
        return changed == 1


def _roles_from_settings(value) -> tuple[str, ...]:
    try:
        settings = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return ()
    if not isinstance(settings, dict) or not isinstance(settings.get("roles"), list):
        return ()
    return tuple(
        role.strip()
        for role in settings["roles"]
        if isinstance(role, str) and role.strip()
    )

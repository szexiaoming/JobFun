"""Opaque bearer-token issuing and authentication use cases."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.repositories.contracts import AuthPrincipal, AuthRepository


MIN_TOKEN_LENGTH = 32
MAX_TOKEN_LENGTH = 512


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    expires_at: str


class AuthenticationService:
    def __init__(self, repository: AuthRepository):
        self._repository = repository

    def authenticate(self, token: str) -> AuthPrincipal | None:
        if not _valid_token_shape(token):
            return None
        now = _utc_now()
        token_hash = hash_token(token)
        principal = self._repository.find_principal_by_token_hash(token_hash, now)
        if principal:
            self._repository.touch_token(token_hash, now)
        return principal

    def issue_token(
        self,
        *,
        user_id: int,
        label: str = "",
        lifetime: timedelta = timedelta(days=30),
    ) -> IssuedToken | None:
        if lifetime <= timedelta(0):
            raise ValueError("Token lifetime must be positive")
        created_at = _utc_now()
        expires_at = (datetime.now(timezone.utc) + lifetime).isoformat()
        token = secrets.token_urlsafe(32)
        token_id = self._repository.create_token(
            user_id=user_id,
            token_hash=hash_token(token),
            label=label.strip()[:100],
            expires_at=expires_at,
            created_at=created_at,
        )
        if token_id is None:
            return None
        return IssuedToken(token=token, expires_at=expires_at)

    def revoke_token(self, *, user_id: int, token_id: int) -> bool:
        if user_id <= 0 or token_id <= 0:
            return False
        return self._repository.revoke_token(
            user_id=user_id,
            token_id=token_id,
            revoked_at=_utc_now(),
        )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _valid_token_shape(token: str) -> bool:
    return MIN_TOKEN_LENGTH <= len(token) <= MAX_TOKEN_LENGTH and token.isascii()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

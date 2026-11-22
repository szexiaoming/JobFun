"""Request-scoped infrastructure wiring for the HTTP adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends

import config
from src.db.postgres_client import PostgresDatabase
from src.db.sqlite_client import Database
from src.repositories.contracts import AuthRepository
from src.repositories.sqlite_auth import SQLiteAuthRepository
from src.services.authentication import AuthenticationService


async def get_database() -> AsyncIterator[Database | PostgresDatabase]:
    if config.DATABASE_BACKEND == "sqlite":
        database = Database()
    elif config.DATABASE_BACKEND == "postgres":
        database = PostgresDatabase(config.POSTGRES_DSN)
    else:
        raise RuntimeError(f"Unsupported database backend: {config.DATABASE_BACKEND}")
    try:
        yield database
    finally:
        database.close()


async def get_auth_repository(
    database: Annotated[Database, Depends(get_database)],
) -> AuthRepository:
    return SQLiteAuthRepository(database)


async def get_authentication_service(
    repository: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> AuthenticationService:
    return AuthenticationService(repository)

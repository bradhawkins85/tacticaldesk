from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .config import get_settings
from app.models import Base

def _resolve_migrations_dir() -> Path:
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        candidate = parent / "migrations"
        if candidate.is_dir():
            return candidate
    raise RuntimeError("Migrations directory not found. Ensure a 'migrations' folder exists.")


MIGRATIONS_DIR = _resolve_migrations_dir()


_ENGINE_LOCK = asyncio.Lock()
_ENGINE: AsyncEngine | None = None
_SESSION_FACTORY: sessionmaker[AsyncSession] | None = None


def _load_migration_files() -> Iterable[Path]:
    return sorted(path for path in MIGRATIONS_DIR.glob("*.sql") if path.is_file())


def _parse_statements(raw_sql: str, dialect_name: str) -> list[str]:
    statements: list[str] = []
    current_dialects = {"all"}
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if not buffer:
            return
        statement = "\n".join(buffer).strip()
        if statement and ("all" in current_dialects or dialect_name in current_dialects):
            statements.extend(stmt.strip() for stmt in statement.split(";") if stmt.strip())
        buffer = []

    directive_pattern = re.compile(r"^--\s*dialect:\s*(?P<dialects>[a-z, ]+)$")

    for line in raw_sql.splitlines():
        stripped = line.strip()
        match = directive_pattern.match(stripped.lower())
        if match:
            flush()
            dialects = {dialect.strip() for dialect in match.group("dialects").split(",") if dialect.strip()}
            current_dialects = dialects or {"all"}
            continue
        if stripped.startswith("--"):
            continue
        buffer.append(line)

    flush()
    return statements


async def apply_migrations(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL UNIQUE,
                    applied_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
                )
                """
            )
        )

        result = await conn.execute(text("SELECT filename FROM schema_migrations"))
        applied = {row[0] for row in result.fetchall()}

        for migration in _load_migration_files():
            if migration.name in applied:
                continue
            statements = _parse_statements(migration.read_text(), conn.dialect.name)
            for statement in statements:
                await conn.execute(text(statement))
            await conn.execute(
                text("INSERT INTO schema_migrations (filename) VALUES (:filename)"),
                {"filename": migration.name},
            )


def create_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.resolved_database_url, future=True, echo=False)


def create_session_factory(engine: AsyncEngine) -> sessionmaker:
    return sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await apply_migrations(engine)


async def get_engine() -> AsyncEngine:
    global _ENGINE, _SESSION_FACTORY

    if _ENGINE is None:
        async with _ENGINE_LOCK:
            if _ENGINE is None:
                engine = create_engine()
                await init_db(engine)
                _ENGINE = engine
                _SESSION_FACTORY = create_session_factory(engine)
    assert _ENGINE is not None
    return _ENGINE


async def dispose_engine() -> None:
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        await _ENGINE.dispose()
        _ENGINE = None
        _SESSION_FACTORY = None


async def get_session() -> AsyncSession:
    await get_engine()
    assert _SESSION_FACTORY is not None
    async_session = _SESSION_FACTORY
    async with async_session() as session:
        yield session

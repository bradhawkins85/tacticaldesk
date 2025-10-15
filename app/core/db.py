from __future__ import annotations

from pathlib import Path
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def _load_migration_files() -> Iterable[Path]:
    return sorted(path for path in MIGRATIONS_DIR.glob("*.sql") if path.is_file())


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
            statements = [stmt.strip() for stmt in migration.read_text().split(";") if stmt.strip()]
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
    await apply_migrations(engine)


async def get_session() -> AsyncSession:
    engine = create_engine()
    async_session = create_session_factory(engine)
    async with engine.begin():
        await apply_migrations(engine)
    async with async_session() as session:
        yield session
    await engine.dispose()

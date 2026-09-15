"""PostgreSQL connection manager.

Creates the SQLAlchemy engine, session factory, declarative base and the
FastAPI dependency used for dependency-injected sessions.
"""
from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import BigInteger, Integer, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger("mira.db")


def _pg_serial(pg_cls, py_cls):
    """Postgres SERIAL/BIGSERIAL type with a SQLite INTEGER variant.

    Falls back to the plain Python type on non-standard (reduced) SQLAlchemy
    builds where the dialect serial classes are unavailable; in that case
    tables should be created from the reference DDL script (SERIAL) instead.
    """
    try:
        pg_type = pg_cls()
    except AttributeError:  # pragma: no cover - reduced SQLAlchemy builds
        pg_type = py_cls()
    return pg_type.with_variant(Integer, "sqlite")


def serial_pk():
    """PRIMARY KEY type: SERIAL on PostgreSQL, INTEGER on SQLite (dev fallback).

    Matches the reference schema (SERIAL / BIGSERIAL) so auto-increment
    behaviour is identical whether tables come from our create_all() or
    from the reference DDL script.
    """
    try:
        from sqlalchemy.dialects.postgresql import SERIAL as _SERIAL
    except ImportError:  # pragma: no cover
        _SERIAL = None
    if _SERIAL is None:
        return Integer().with_variant(Integer, "sqlite")
    return _pg_serial(_SERIAL, Integer)


def bigserial_pk():
    """BIGSERIAL on PostgreSQL, INTEGER on SQLite."""
    try:
        from sqlalchemy.dialects.postgresql import BIGSERIAL as _BIGSERIAL
    except ImportError:  # pragma: no cover
        _BIGSERIAL = None
    if _BIGSERIAL is None:
        return BigInteger().with_variant(Integer, "sqlite")
    return _pg_serial(_BIGSERIAL, BigInteger)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=True,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables that do not exist yet.

    In production Alembic migrations should own the schema; this is the
    dev/demo convenience path and is safe (CREATE TABLE IF NOT EXISTS).
    """
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ensured (Base.metadata.create_all)")


def check_db_connection() -> bool:
    """Return True when a simple SELECT 1 succeeds."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - depends on environment
        logger.warning("PostgreSQL connection check failed: %s", exc)
        return False


def seed_default_data() -> None:
    """Idempotent seed: default CPSEs + one admin user (dev/demo)."""
    from app.models.cpse import Cpse
    from app.models.user import User
    from app.core.security import hash_password
    from app.utils.constants import DEFAULT_CPSES, ROLE_ADMIN

    db = SessionLocal()
    try:
        for cpse_info in DEFAULT_CPSES:
            existing = (
                db.query(Cpse).filter(Cpse.short_code == cpse_info["short_code"]).first()
            )
            if existing is None:
                db.add(Cpse(name=cpse_info["name"], short_code=cpse_info["short_code"]))
                logger.info("Seeded CPSE: %s", cpse_info["short_code"])

        admin = (
            db.query(User).filter(User.email == settings.SEED_ADMIN_EMAIL).first()
        )
        if admin is None:
            db.add(
                User(
                    email=settings.SEED_ADMIN_EMAIL,
                    password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
                    full_name="MIRA Administrator",
                    role=ROLE_ADMIN,
                    is_active=True,
                )
            )
            logger.info("Seeded admin user: %s", settings.SEED_ADMIN_EMAIL)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

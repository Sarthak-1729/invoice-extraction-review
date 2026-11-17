"""SQLAlchemy 2.0 models and session setup (SQLite).

Schema creation: ``create_schema()`` runs ``Base.metadata.create_all()`` at
startup, which creates missing tables and never alters existing ones. There
is no migration tool yet; if the schema changes once real data exists, add
Alembic then. The SQLite file lives under the git-ignored data/ directory.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

STATUSES = ("extracted", "needs_review", "approved", "failed")


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso_utc(value: datetime | None) -> str | None:
    """ISO 8601 with an explicit UTC offset. SQLite stores no time zone, so
    values read back are naive; they were written in UTC by ``utcnow``."""
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4 hex
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))  # sanitized, display only
    stored_name: Mapped[str] = mapped_column(String(64))  # "<uuid>.pdf", never user input
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer)
    document_text: Mapped[str] = mapped_column(Text)  # PDF text, for re-validation

    status: Mapped[str] = mapped_column(String(20), index=True)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)

    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    prompt_hash: Mapped[str | None] = mapped_column(String(64))

    # Current values: raw strings (as extracted, then as corrected) and the
    # normalized invoice built from them.
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    normalized: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Field paths a reviewer has corrected: grounding is not applied to them.
    corrected_paths: Mapped[list[str]] = mapped_column(JSON, default=list)

    acknowledged_open_flags: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    flags: Mapped[list["FlagRow"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="FlagRow.id"
    )
    corrections: Mapped[list["Correction"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Correction.id"
    )


class FlagRow(Base):
    __tablename__ = "flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    field_path: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)

    document: Mapped[Document] = relationship(back_populates="flags")


class Correction(Base):
    """Audit trail: one row per changed field, never updated or deleted."""

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    field_path: Mapped[str] = mapped_column(String(100))
    original_value: Mapped[str | None] = mapped_column(Text)
    corrected_value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="corrections")


def make_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args={"check_same_thread": False})


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        yield session

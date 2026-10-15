from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base. Schema changes are made by migrations, never by ``create_all``."""


def utcnow() -> datetime:
    return datetime.now(UTC)

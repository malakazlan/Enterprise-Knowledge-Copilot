"""Shared SQLAlchemy column types."""

from __future__ import annotations

import enum

from sqlalchemy import Enum


def portable_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """A database-agnostic enum column.

    Stored as ``VARCHAR`` with a ``CHECK`` constraint (no native PG enum, so
    migrations stay portable). ``values_callable`` persists the member *values*
    (e.g. ``"admin"``) rather than SQLAlchemy's default of member *names*
    (``"ADMIN"``) — keeping stored data, API payloads, and CHECK constraints
    consistent across SQLite and PostgreSQL.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=20,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )

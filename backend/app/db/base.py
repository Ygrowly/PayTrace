"""Declarative base for SQLAlchemy ORM.

Per ADR 0003, we do NOT declare DB-level FOREIGN KEY constraints; cross-table
references are expressed via plain columns plus indexes, and integrity is
enforced at the application layer.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

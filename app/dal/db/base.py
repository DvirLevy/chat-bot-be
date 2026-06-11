"""Declarative base for all ORM models.

A single ``Base`` is shared by every ORM model and by Alembic's
``target_metadata`` so that autogenerate and ``create_all`` see the full
schema.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common declarative base for ORM models."""

    pass

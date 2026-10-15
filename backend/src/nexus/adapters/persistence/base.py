"""Declarative base, naming convention and column helpers."""

from enum import StrEnum

from sqlalchemy import CheckConstraint, MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def values_check(column: str, values: type[StrEnum]) -> CheckConstraint:
    """`CHECK (column IN (...))` built from the StrEnum, which is the source of truth."""
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_values")

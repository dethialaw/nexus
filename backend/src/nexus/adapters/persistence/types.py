"""Column types. numpy stays here: the core only sees `tuple[float, ...]`."""

from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

from nexus.core.shared.entities import EMBEDDING_DIMENSIONS


class Vector(TypeDecorator[tuple[float, ...]]):
    """`vector(768)` read and written as a tuple of floats."""

    impl = VECTOR(EMBEDDING_DIMENSIONS)
    cache_ok = True

    def process_bind_param(self, value: tuple[float, ...] | None, dialect: Dialect) -> Any:
        return None if value is None else list(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> tuple[float, ...] | None:
        return None if value is None else tuple(float(x) for x in value)

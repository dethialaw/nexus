"""Reads the Source Catalog shipped with the package; the core validates its blocks."""

import tomllib
from importlib.resources import files
from typing import Any

from nexus.core.ingestion.source_catalog import RawSourceCatalog, UnreadableCatalogError

CATALOG_FILE = "source_catalog.toml"


def parse_source_catalog(text: str) -> RawSourceCatalog:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise UnreadableCatalogError(str(error)) from error
    sources = _tables(raw, "source")
    retired = _tables(raw, "retired")
    if not all(isinstance(table.get("source_key"), str) for table in retired):
        raise UnreadableCatalogError("every [[retired]] needs a source_key string")
    return RawSourceCatalog(
        sources=tuple(sources), retired=tuple(table["source_key"] for table in retired)
    )


def _tables(raw: dict[str, Any], name: str) -> list[dict[str, Any]]:
    tables = raw.get(name, [])
    if not isinstance(tables, list) or not all(isinstance(table, dict) for table in tables):
        raise UnreadableCatalogError(f"{name} must be an array of tables: [[{name}]]")
    return tables


class TomlSourceCatalog:
    def read(self) -> RawSourceCatalog:
        text = files(__package__).joinpath(CATALOG_FILE).read_text(encoding="utf-8")
        return parse_source_catalog(text)

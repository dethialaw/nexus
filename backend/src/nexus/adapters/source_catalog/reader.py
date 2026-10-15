"""Reads the Source Catalog shipped with the package."""

import tomllib
from importlib.resources import files

from nexus.core.ingestion.source_catalog import SourceCatalog

CATALOG_FILE = "source_catalog.toml"


def parse_source_catalog(text: str) -> SourceCatalog:
    raw = tomllib.loads(text)
    return SourceCatalog.model_validate(
        {
            "sources": [{"config": source} for source in raw.get("source", [])],
            "retired": [retired["source_key"] for retired in raw.get("retired", [])],
        }
    )


def load_source_catalog() -> SourceCatalog:
    text = files(__package__).joinpath(CATALOG_FILE).read_text(encoding="utf-8")
    return parse_source_catalog(text)

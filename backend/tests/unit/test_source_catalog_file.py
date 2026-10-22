import pytest

from nexus.adapters.source_catalog.reader import TomlSourceCatalog, parse_source_catalog
from nexus.core.ingestion.source_catalog import SourceCatalog, UnreadableCatalogError
from nexus.core.ingestion.source_config import RssConfig


def test_shipped_catalog_lists_the_ten_initial_feeds() -> None:
    catalog = SourceCatalog.from_raw(TomlSourceCatalog().read())

    configs = [entry.config for entry in catalog.sources]
    assert len(configs) == 10
    assert all(isinstance(config, RssConfig) for config in configs)
    excluded = {
        config.source_key: config.exclude_url_patterns
        for config in configs
        if isinstance(config, RssConfig) and config.exclude_url_patterns
    }
    assert excluded == {"rss:rmcsport.bfmtv.com/rss/football": ("_DN-",)}


def test_parse_returns_both_tables_unvalidated() -> None:
    raw = parse_source_catalog(
        """
        [[source]]
        connector = "reddit"
        subreddit = "r/not-validated-here"

        [[retired]]
        source_key = "reddit:python"
        """
    )

    assert raw.sources == ({"connector": "reddit", "subreddit": "r/not-validated-here"},)
    assert raw.retired == ("reddit:python",)


@pytest.mark.parametrize(
    "text",
    [
        "[[source]]\nconnector = ",
        '[[retired]]\nkey = "reddit:python"',
        'source = "not a table"',
    ],
)
def test_parse_rejects_an_unreadable_catalog(text: str) -> None:
    with pytest.raises(UnreadableCatalogError):
        parse_source_catalog(text)

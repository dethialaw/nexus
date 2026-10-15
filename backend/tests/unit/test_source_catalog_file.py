import pytest
from pydantic import ValidationError

from nexus.adapters.source_catalog.reader import load_source_catalog, parse_source_catalog


def test_shipped_catalog_is_valid() -> None:
    load_source_catalog()


def test_parse_reads_both_tables() -> None:
    catalog = parse_source_catalog(
        """
        [[source]]
        connector = "rss"
        feed_url = "https://www.lemonde.fr/rss/une.xml"

        [[retired]]
        source_key = "reddit:python"
        """
    )

    assert [entry.source_key for entry in catalog.sources] == ["rss:lemonde.fr/rss/une.xml"]
    assert catalog.retired == ("reddit:python",)


def test_parse_rejects_a_key_both_listed_and_retired() -> None:
    with pytest.raises(ValidationError):
        parse_source_catalog(
            """
            [[source]]
            connector = "reddit"
            subreddit = "python"

            [[retired]]
            source_key = "reddit:python"
            """
        )

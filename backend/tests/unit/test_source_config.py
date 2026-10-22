import pytest
from pydantic import TypeAdapter, ValidationError

from nexus.core.ingestion.source_config import (
    HackerNewsConfig,
    RedditConfig,
    RssConfig,
    SourceConfig,
    normalize_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.lemonde.fr/rss/une.xml",
        "http://lemonde.fr/rss/une.xml/",
        "https://WWW.LeMonde.FR/rss/une.xml",
    ],
)
def test_normalize_url_ignores_scheme_www_trailing_slash_and_host_case(url: str) -> None:
    assert normalize_url(url) == "lemonde.fr/rss/une.xml"


def test_normalize_url_keeps_path_case_and_query() -> None:
    assert normalize_url("https://example.com/Feed?Lang=FR") == "example.com/Feed?Lang=FR"


def test_normalize_url_rejects_relative_url() -> None:
    with pytest.raises(ValueError, match="absolute"):
        normalize_url("lemonde.fr/rss")


def test_source_keys() -> None:
    assert RssConfig(feed_url="https://www.lemonde.fr/rss/une.xml/").source_key == (
        "rss:lemonde.fr/rss/une.xml"
    )
    assert RedditConfig(subreddit="Python").source_key == "reddit:python"
    assert HackerNewsConfig(feed="top").source_key == "hackernews:top"


def test_exclude_url_patterns_do_not_change_the_source_key() -> None:
    plain = RssConfig(feed_url="https://rmcsport.bfmtv.com/rss/football/")
    filtered = RssConfig(
        feed_url="https://rmcsport.bfmtv.com/rss/football/", exclude_url_patterns=("_DN-",)
    )

    assert plain.exclude_url_patterns == ()
    assert filtered.exclude_url_patterns == ("_DN-",)
    assert filtered.source_key == plain.source_key


def test_config_is_picked_by_connector() -> None:
    config = TypeAdapter(SourceConfig).validate_python({"connector": "reddit", "subreddit": "rust"})
    assert isinstance(config, RedditConfig)


@pytest.mark.parametrize(
    "raw",
    [
        {"connector": "rss", "feed_url": "ftp://example.com/feed"},
        {"connector": "rss", "feed_url": "http://example.com/feed"},
        {"connector": "rss", "feed_url": "https://example.com/feed", "exclude_url_patterns": [""]},
        {"connector": "reddit", "subreddit": "r/python"},
        {"connector": "hackernews", "feed": "top", "extra": 1},
        {"connector": "unknown"},
    ],
)
def test_invalid_config_is_rejected(raw: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SourceConfig).validate_python(raw)

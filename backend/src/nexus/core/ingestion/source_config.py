"""Per-Connector Source configuration and construction of the `source_key`."""

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexus.core.ingestion.entities import Connector


def normalize_url(url: str) -> str:
    """Drop the scheme, a leading `www.` and a trailing slash; lowercase the host.

    The path and query keep their case: only the host is case-insensitive.
    """
    parts = urlsplit(url.strip())
    if not parts.netloc:
        raise ValueError(f"not an absolute URL: {url!r}")
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{host}{path}{query}"


class _SourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RssConfig(_SourceConfig):
    connector: Literal[Connector.RSS] = Connector.RSS
    feed_url: str

    @field_validator("feed_url")
    @classmethod
    def _absolute_http_url(cls, value: str) -> str:
        if urlsplit(value).scheme not in {"http", "https"}:
            raise ValueError("feed_url must be an http(s) URL")
        normalize_url(value)
        return value

    @property
    def source_key(self) -> str:
        return f"{Connector.RSS}:{normalize_url(self.feed_url)}"


class HackerNewsConfig(_SourceConfig):
    connector: Literal[Connector.HACKERNEWS] = Connector.HACKERNEWS
    feed: Literal["top", "best", "new"]

    @property
    def source_key(self) -> str:
        return f"{Connector.HACKERNEWS}:{self.feed}"


class RedditConfig(_SourceConfig):
    connector: Literal[Connector.REDDIT] = Connector.REDDIT
    subreddit: Annotated[str, Field(pattern=r"^[A-Za-z0-9_]{2,21}$")]

    @property
    def source_key(self) -> str:
        # Subreddit names are case-insensitive.
        return f"{Connector.REDDIT}:{self.subreddit.lower()}"


SourceConfig = Annotated[
    RssConfig | HackerNewsConfig | RedditConfig, Field(discriminator="connector")
]

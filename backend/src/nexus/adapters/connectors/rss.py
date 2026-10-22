"""RSS Connector: RSS 2.0 and Atom, read with feedparser from bytes, never from a URL."""

import io
from calendar import timegm
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import feedparser

from nexus.adapters.connectors.xml_guard import check_xml
from nexus.core.ingestion.entities import RawArticle, RawArticleBatch, Source
from nexus.core.ingestion.errors import CollectionError
from nexus.core.ingestion.source_config import RssConfig
from nexus.core.shared.ports import FetchError, FetchUsage, HttpFetcher


class RssConnector:
    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    async def read(self, source: Source) -> RawArticleBatch:
        config = RssConfig.model_validate(source.config)
        try:
            response = await self._fetcher.fetch(config.feed_url, FetchUsage.FEED)
        except FetchError as error:
            raise CollectionError(str(error)) from error
        if not 200 <= response.status < 300:
            raise CollectionError(f"HTTP {response.status}")
        return parse_feed(response.body, config.feed_url)


def parse_feed(body: bytes, feed_url: str = "") -> RawArticleBatch:
    check_xml(body)
    # A stream, so feedparser can never take the input for a URL to fetch.
    parsed = feedparser.parse(io.BytesIO(body))
    if not parsed.get("version"):
        raise CollectionError("not a feed: no RSS or Atom document found")
    readable = [raw for entry in parsed.entries if (raw := _raw_article(entry)) is not None]
    return RawArticleBatch(
        raw_articles=tuple(readable),
        unreadable_count=len(parsed.entries) - len(readable),
        base_url=feed_url,
    )


def _raw_article(entry: Any) -> RawArticle | None:
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip() or _guid_url(entry)
    if not title or not link:
        return None
    contents = [item.get("value") or "" for item in entry.get("content") or []]
    # `content:encoded` (or Atom content) wins over the description when it is longer.
    text = max([entry.get("summary") or "", *contents], key=len)
    return RawArticle(title=title, link=link, text=text, published_at=_date(entry))


def _guid_url(entry: Any) -> str:
    guid = (entry.get("id") or "").strip()
    return guid if urlsplit(guid).scheme in ("http", "https") else ""


def _date(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return None if parsed is None else datetime.fromtimestamp(timegm(parsed), tz=UTC)

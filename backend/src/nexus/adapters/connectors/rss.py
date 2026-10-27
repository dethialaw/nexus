"""RSS Connector: RSS 2.0 and Atom, read with feedparser from bytes, never from a URL."""

import io
from calendar import timegm
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import feedparser

from nexus.adapters.connectors.xml_guard import check_xml
from nexus.core.ingestion.entities import (
    Anomaly,
    AnomalyKind,
    Connector,
    FeedCheck,
    FeedItem,
    FeedItemStatus,
    RawArticle,
    RawArticleBatch,
    Source,
)
from nexus.core.ingestion.errors import CollectionError
from nexus.core.ingestion.normalization import normalize_batch
from nexus.core.ingestion.source_config import RssConfig
from nexus.core.shared.ports import (
    FetchError,
    FetchResponse,
    FetchUsage,
    HttpFetcher,
    HttpValidators,
)


class RssConnector:
    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    async def read(self, source: Source) -> RawArticleBatch:
        config = RssConfig.model_validate(source.config)
        try:
            response = await self._fetcher.fetch(
                config.feed_url, FetchUsage.FEED, source.validators
            )
        except FetchError as error:
            raise CollectionError(str(error)) from error
        if response.status == 304:
            return RawArticleBatch(
                raw_articles=(),
                unreadable_count=0,
                validators=HttpValidators(
                    etag=(
                        source.validators.etag
                        if response.validators.etag is None
                        else response.validators.etag
                    ),
                    last_modified=(
                        source.validators.last_modified
                        if response.validators.last_modified is None
                        else response.validators.last_modified
                    ),
                ),
                anomalies=_moved(config.feed_url, response),
            )
        if not 200 <= response.status < 300:
            raise CollectionError(f"HTTP {response.status}")
        return replace(
            parse_feed(response.body, config.feed_url),
            validators=response.validators,
            anomalies=_moved(config.feed_url, response),
        )


async def check_feed(
    fetcher: HttpFetcher,
    feed_url: str,
    exclude_url_patterns: tuple[str, ...] = (),
    *,
    now: datetime,
) -> FeedCheck:
    """Fetch and read a feed as a Collection does, without storing anything.

    Raises `CollectionError`, with its cause, when a Collection would fail.
    """
    config = RssConfig(feed_url=feed_url, exclude_url_patterns=exclude_url_patterns)
    try:
        response = await fetcher.fetch(config.feed_url, FetchUsage.FEED)
    except FetchError as error:
        raise CollectionError(str(error)) from error
    anomalies = _moved(config.feed_url, response)
    if response.status == 304:
        batch = RawArticleBatch(raw_articles=(), unreadable_count=0, base_url=config.feed_url)
    elif 200 <= response.status < 300:
        batch = parse_feed(response.body, config.feed_url)
    else:
        raise CollectionError(f"HTTP {response.status}")
    source = Source(
        id=0,
        source_key=config.source_key,
        connector=Connector.RSS,
        config=config.model_dump(mode="json"),
        owner_user_id=None,
        deactivation_reason=None,
        last_collected_at=None,
    )
    items = []
    for raw in batch.raw_articles:
        articles, excluded = normalize_batch(replace(batch, raw_articles=(raw,)), source, now)
        status = (
            FeedItemStatus.EXCLUDED
            if excluded
            else FeedItemStatus.KEPT
            if articles
            else FeedItemStatus.TOO_OLD
        )
        items.append(FeedItem(raw.title, raw.link, raw.published_at, status))
    return FeedCheck(
        feed_url=config.feed_url,
        final_url=response.final_url,
        status=response.status,
        not_modified=response.status == 304,
        validators=response.validators,
        items=tuple(items),
        unreadable_count=batch.unreadable_count,
        excluded_count=sum(item.status is FeedItemStatus.EXCLUDED for item in items),
        anomalies=anomalies,
    )


def _moved(feed_url: str, response: FetchResponse) -> tuple[Anomaly, ...]:
    if not response.moved_permanently:
        return ()
    return (
        Anomaly(AnomalyKind.FEED_MOVED, f"{feed_url} moved permanently to {response.final_url}"),
    )


def parse_feed(body: bytes, feed_url: str = "") -> RawArticleBatch:
    check_xml(body)
    # A stream, so feedparser can never take the input for a URL to fetch.
    parsed = feedparser.parse(io.BytesIO(body))
    if not parsed.get("version"):
        raise CollectionError("not a feed: no RSS or Atom document found")
    readable = [raw for entry in parsed.entries if (raw := _raw_article(entry)) is not None]
    if parsed.entries and not readable:
        raise CollectionError(f"all {len(parsed.entries)} feed items are unreadable")
    return RawArticleBatch(
        raw_articles=tuple(readable),
        unreadable_count=len(parsed.entries) - len(readable),
        base_url=feed_url,
    )


def _raw_article(entry: Any) -> RawArticle | None:
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip()
    guid = (entry.get("id") or "").strip()
    if not link or (link == guid and not _is_url(guid)):
        # feedparser copies a guid into `link` itself, whether or not it is a URL.
        link = guid if _is_url(guid) else ""
    if not title or not link:
        return None
    contents = [item.get("value") or "" for item in entry.get("content") or []]
    # `content:encoded` (or Atom content) wins over the description when it is longer.
    text = max([entry.get("summary") or "", *contents], key=len)
    return RawArticle(title=title, link=link, text=text, published_at=_date(entry))


def _is_url(value: str) -> bool:
    return urlsplit(value).scheme in ("http", "https")


def _date(entry: Any) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return None if parsed is None else datetime.fromtimestamp(timegm(parsed), tz=UTC)

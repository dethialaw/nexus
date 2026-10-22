"""Raw Article -> Article: the normalization rules of spec 0002."""

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import urldefrag, urljoin

from nexus.core.ingestion.entities import (
    Article,
    ExcerptOrigin,
    LinkedPageStatus,
    RawArticle,
    RawArticleBatch,
    Source,
)

FINGERPRINT_EXCERPT_CHARS = 500
EXCERPT_MAX_CHARS = 3000
RETENTION_WINDOW = timedelta(days=30)
FUTURE_TOLERANCE = timedelta(minutes=15)

# Closed list of tracking parameters, plus every `utm_*`.
TRACKING_PARAMETERS = frozenset(
    {
        "xtor",
        "fbclid",
        "gclid",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "at_medium",
        "at_campaign",
        "at_source",
        "at_creation",
        "at_variant",
        "at_format",
        "at_link",
        "at_send_date",
        "at_account",
    }
)

_BLOCKS = re.compile(r"<(script|style)\b.*?</\1\s*>|<!--.*?-->", re.IGNORECASE | re.DOTALL)
_TAGS = re.compile(r"</?[A-Za-z][^>]*>")


def normalize_batch(
    batch: RawArticleBatch, source: Source, collected_at: datetime
) -> tuple[list[Article], int]:
    """Articles ready to insert, and the number of items excluded by the Source's patterns.

    Items older than the retention window are dropped silently: they are neither excluded
    nor unreadable. Items are never assumed to be sorted.
    """
    patterns = tuple(source.config.get("exclude_url_patterns") or ())
    articles: list[Article] = []
    excluded = 0
    for raw in batch.raw_articles:
        url = canonical_url(raw.link, batch.base_url)
        if any(pattern in url for pattern in patterns):
            excluded += 1
            continue
        published_at = plausible_date(raw.published_at, collected_at)
        if published_at < collected_at - RETENTION_WINDOW:
            continue
        articles.append(to_article(raw, source.id, collected_at, url, published_at))
    return articles, excluded


def to_article(
    raw: RawArticle,
    source_id: int,
    collected_at: datetime,
    url: str | None = None,
    published_at: datetime | None = None,
) -> Article:
    url = canonical_url(raw.link) if url is None else url
    excerpt = clean_excerpt(raw.text)
    return Article(
        source_id=source_id,
        canonical_url=url,
        linked_url=url,
        linked_page_status=LinkedPageStatus.PENDING,
        title=raw.title,
        excerpt=excerpt,
        excerpt_origin=ExcerptOrigin.SOURCE,
        fingerprint=fingerprint(raw.title, excerpt),
        published_at=published_at or plausible_date(raw.published_at, collected_at),
        collected_at=collected_at,
    )


def canonical_url(link: str, base_url: str = "") -> str:
    """Absolute, without fragment or tracking parameters; scheme, `www` and path case kept."""
    url, _ = urldefrag(urljoin(base_url, link.strip()))
    base, separator, query = url.partition("?")
    if not separator:
        return url
    kept = [part for part in query.split("&") if not _is_tracking(part)]
    return f"{base}?{'&'.join(kept)}" if kept else base


def _is_tracking(parameter: str) -> bool:
    name = parameter.partition("=")[0].lower()
    return name in TRACKING_PARAMETERS or name.startswith("utm_")


def plausible_date(published_at: datetime | None, collected_at: datetime) -> datetime:
    if published_at is None or published_at > collected_at + FUTURE_TOLERANCE:
        return collected_at
    return published_at


def clean_excerpt(text: str) -> str:
    """Plain text: HTML removed, entities decoded (even escaped twice), capped."""
    text = _BLOCKS.sub(" ", text)
    text = html.unescape(_TAGS.sub(" ", text))
    # Entities decoded once may reveal escaped markup.
    text = html.unescape(_TAGS.sub(" ", _BLOCKS.sub(" ", text)))
    return " ".join(text.split())[:EXCERPT_MAX_CHARS]


def fingerprint(title: str, excerpt: str) -> str:
    """SHA-256 of the normalized title, then the first normalized characters of the Excerpt."""
    content = f"{_normalize(title)}\n{_normalize(excerpt)[:FINGERPRINT_EXCERPT_CHARS]}"
    return hashlib.sha256(content.encode()).hexdigest()


def _normalize(text: str) -> str:
    """Lowercase, punctuation removed, whitespace collapsed."""
    kept = "".join(c for c in text.lower() if not unicodedata.category(c).startswith("P"))
    return " ".join(kept.split())

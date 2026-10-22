"""Raw Article -> Article: the normalization rules of spec 0002."""

import hashlib
import unicodedata
from datetime import datetime

from nexus.core.ingestion.entities import Article, ExcerptOrigin, LinkedPageStatus, RawArticle

FINGERPRINT_EXCERPT_CHARS = 500


def to_article(raw: RawArticle, source_id: int, collected_at: datetime) -> Article:
    return Article(
        source_id=source_id,
        canonical_url=raw.link,
        linked_url=raw.link,
        linked_page_status=LinkedPageStatus.PENDING,
        title=raw.title,
        excerpt=raw.text,
        excerpt_origin=ExcerptOrigin.SOURCE,
        fingerprint=fingerprint(raw.title, raw.text),
        published_at=raw.published_at or collected_at,
        collected_at=collected_at,
    )


def fingerprint(title: str, excerpt: str) -> str:
    """SHA-256 of the normalized title, then the first normalized characters of the Excerpt."""
    content = f"{_normalize(title)}\n{_normalize(excerpt)[:FINGERPRINT_EXCERPT_CHARS]}"
    return hashlib.sha256(content.encode()).hexdigest()


def _normalize(text: str) -> str:
    """Lowercase, punctuation removed, whitespace collapsed."""
    kept = "".join(c for c in text.lower() if not unicodedata.category(c).startswith("P"))
    return " ".join(kept.split())

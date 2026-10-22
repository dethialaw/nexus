"""Seam 1: the RSS Connector composed with the core normalization.

Every feed here is synthetic, written by hand: no publisher content is committed.
"""

from datetime import UTC, datetime

import pytest

from nexus.adapters.connectors.rss import parse_feed
from nexus.core.ingestion.entities import Article, ExcerptOrigin, LinkedPageStatus
from nexus.core.ingestion.errors import CollectionError
from nexus.core.ingestion.normalization import to_article

COLLECTED_AT = datetime(2026, 10, 21, 6, 0, tzinfo=UTC)

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Example</title><link>https://example.com/</link>
  <item>
    <title>First headline</title>
    <link>https://example.com/first</link>
    <description>Alpha text.</description>
    <pubDate>Tue, 20 Oct 2026 08:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Second headline</title>
    <link>https://example.com/second</link>
    <description>Beta text.</description>
  </item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example</title><id>urn:example</id><updated>2026-10-20T09:00:00Z</updated>
  <entry>
    <title>Atom headline</title>
    <link href="https://example.com/atom"/>
    <id>urn:example:1</id>
    <updated>2026-10-20T09:00:00Z</updated>
    <summary>Gamma text.</summary>
  </entry>
</feed>"""


def read(body: bytes) -> list[Article]:
    return [to_article(raw, 1, COLLECTED_AT) for raw in parse_feed(body).raw_articles]


def test_rss_items_become_articles() -> None:
    first, second = read(RSS)

    assert (first.title, first.canonical_url, first.excerpt) == (
        "First headline",
        "https://example.com/first",
        "Alpha text.",
    )
    assert first.published_at == datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    assert (first.source_id, first.collected_at) == (1, COLLECTED_AT)
    assert first.excerpt_origin is ExcerptOrigin.SOURCE
    assert (first.linked_url, first.linked_page_status) == (
        "https://example.com/first",
        LinkedPageStatus.PENDING,
    )
    assert second.published_at == COLLECTED_AT


def test_atom_entries_become_articles() -> None:
    [entry] = read(ATOM)

    assert (entry.title, entry.canonical_url, entry.excerpt) == (
        "Atom headline",
        "https://example.com/atom",
        "Gamma text.",
    )
    assert entry.published_at == datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def one_item(title: str, link: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>E</title>'
        f"<item><title>{title}</title><link>{link}</link><description>Same text.</description>"
        "</item></channel></rss>"
    ).encode()


def test_fingerprint_ignores_case_spacing_and_punctuation_of_the_title() -> None:
    [original] = read(one_item("First headline", "https://example.com/a"))
    [republished] = read(one_item("First   HEADLINE!", "https://example.com/b"))
    [other] = read(one_item("Another headline", "https://example.com/c"))

    assert republished.fingerprint == original.fingerprint
    assert other.fingerprint != original.fingerprint
    assert len(original.fingerprint) == 64


@pytest.mark.parametrize(
    ("body", "cause"),
    [
        (b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY x "y">]><rss/>', "DOCTYPE"),
        (b'<?xml version="1.0"?><!doctype rss><rss/>', "DOCTYPE"),
        (b'<?xml version="1.0"?><rss><!-- <!DocType x> --></rss>', "DOCTYPE"),
        (b'<?xml version="1.0"?><rss><!ENTITY x "y"></rss>', "ENTITY"),
        (b'<?xml version="1.0"?><rss><!entity x "y"></rss>', "ENTITY"),
        ('﻿<?xml version="1.0"?><rss/>'.encode("utf-16-le"), "UTF-16"),
        ('﻿<?xml version="1.0"?><rss/>'.encode("utf-16-be"), "UTF-16"),
        ('﻿<?xml version="1.0"?><rss/>'.encode("utf-32-le"), "UTF-32"),
        ('﻿<?xml version="1.0"?><rss/>'.encode("utf-32-be"), "UTF-32"),
        (b'<?xml version="1.0" encoding="UTF-16"?><rss/>', "UTF-16"),
        (b"<?xml version='1.0' encoding='utf-32'?><rss/>", "UTF-32"),
    ],
)
def test_prefilter_refuses_before_parsing(body: bytes, cause: str) -> None:
    with pytest.raises(CollectionError, match=cause):
        parse_feed(body)


def test_unparseable_bytes_are_refused() -> None:
    with pytest.raises(CollectionError, match="not a feed"):
        parse_feed(b"<html><body>Not a feed</body></html>")

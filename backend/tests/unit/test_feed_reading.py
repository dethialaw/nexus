"""Seam 1: the RSS Connector composed with the core normalization.

Every feed here is synthetic, written by hand: no publisher content is committed.
"""

from datetime import UTC, datetime

import feedparser.encodings
import pytest

from nexus.adapters.connectors.rss import parse_feed
from nexus.core.ingestion.entities import (
    Article,
    Connector,
    ExcerptOrigin,
    LinkedPageStatus,
    Source,
)
from nexus.core.ingestion.errors import CollectionError
from nexus.core.ingestion.normalization import normalize_batch

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


FEED_URL = "https://example.com/feeds/main.xml"


def source(*patterns: str) -> Source:
    return Source(
        id=1,
        source_key="rss:example.com/feeds/main.xml",
        connector=Connector.RSS,
        config={"feed_url": FEED_URL, "exclude_url_patterns": patterns},
        owner_user_id=None,
        deactivation_reason=None,
        last_collected_at=None,
    )


def read_counted(body: bytes, *patterns: str) -> tuple[list[Article], int, int]:
    batch = parse_feed(body, FEED_URL)
    articles, excluded = normalize_batch(batch, source(*patterns), COLLECTED_AT)
    return articles, batch.unreadable_count, excluded


def read(body: bytes) -> list[Article]:
    return read_counted(body)[0]


def rss(*items: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" '
        'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>E</title>'
        + "".join(f"<item>{item}</item>" for item in items)
        + "</channel></rss>"
    ).encode()


def item(title: str = "T", link: str = "https://example.com/a", **tags: str) -> str:
    head = f"<title>{title}</title><link>{link}</link>"
    return head + "".join(f"<{tag}>{value}</{tag}>" for tag, value in tags.items())


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
        # Outside the ASCII-compatible list, a DOCTYPE would not show in the raw bytes.
        ('<?xml version="1.0" encoding="cp037"?><rss/>'.encode("cp037"), "cp037"),
        ('<?xml version="1.0"?><rss/>'.encode("cp037"), "cp037"),
        (b'<?xml version="1.0" encoding="shift_jis"?><rss/>', "shift_jis"),
        (b'<?xml version="1.0" encoding="utf-7"?><rss/>', "utf-7"),
        (b'<?xml version="1.0" encoding = "cp500" ?><rss/>', "cp500"),
        (b'<?xml version="1.0" encoding="no-such-codec"?><rss/>', "no-such-codec"),
        (b'\xef\xbb\xbf<?xml version="1.0" encoding="cp037"?><rss/>', "cp037"),
        # feedparser reads the encoding of any leading processing instruction on the line.
        (b'<?xml version="1.0"?><?x encoding="cp037"?><rss/>', "cp037"),
    ],
)
def test_prefilter_refuses_before_parsing(body: bytes, cause: str) -> None:
    with pytest.raises(CollectionError, match=cause):
        parse_feed(body)


@pytest.mark.parametrize(
    "encoding", ["UTF-8", "utf8", "us-ascii", "ISO-8859-1", "latin1", "iso-8859-15", "windows-1252"]
)
def test_ascii_compatible_encodings_are_read(encoding: str) -> None:
    body = (
        f'<?xml version="1.0" encoding="{encoding}"?><rss version="2.0"><channel><title>E</title>'
        "<item><title>Café</title><link>https://example.com/a</link></item></channel></rss>"
    )

    [article] = read(body.encode("utf-8" if encoding.lower().startswith("utf") else "latin-1"))

    assert article.title == "Café"


def test_feedparser_has_no_encoding_guesser() -> None:
    # With chardet installed, feedparser would guess encodings the prefilter never saw.
    assert feedparser.encodings.chardet is None


def test_unparseable_bytes_are_refused() -> None:
    with pytest.raises(CollectionError, match="not a feed"):
        parse_feed(b"<html><body>Not a feed</body></html>")


XXE = b'<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
LAUGHS = b'<!DOCTYPE rss [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
ITEM = b"<item><title>T</title><link>https://example.com/t</link></item>"


@pytest.mark.parametrize("attack", [XXE, LAUGHS, b"<!-- x --><!doctype rss>"])
@pytest.mark.parametrize("malformed", [False, True])
def test_attacks_are_refused_before_parsing_on_well_formed_and_malformed_feeds(
    attack: bytes, malformed: bool
) -> None:
    unclosed = b"<unclosed><&" if malformed else b""
    body = (
        b'<?xml version="1.0"?>'
        + attack
        + b'<rss version="2.0"><channel>'
        + unclosed
        + ITEM
        + b"</channel></rss>"
    )

    with pytest.raises(CollectionError, match="refused before parsing"):
        parse_feed(body)


def test_a_feed_whose_items_are_all_unreadable_is_refused() -> None:
    body = (
        b'<rss version="2.0"><channel><title>E</title><item><title>A</title></item></channel></rss>'
    )

    with pytest.raises(CollectionError, match="unreadable"):
        parse_feed(body)


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ("/news/a", "https://example.com/news/a"),
        ("a", "https://example.com/feeds/a"),
        ("https://example.com/a#part", "https://example.com/a"),
        (
            "https://www.Example.com/A/B?utm_source=x&id=7&xtor=RSS-1&fbclid=z&gclid=y"
            "&at_medium=m&at_campaign=c&UTM_term=t",
            "https://www.Example.com/A/B?id=7",
        ),
        ("http://example.com/a?utm_source=x", "http://example.com/a"),
    ],
)
def test_canonical_url(link: str, expected: str) -> None:
    [article] = read(rss(item(link=link, description="d")))

    assert article.canonical_url == expected
    assert article.linked_url == expected


def test_guid_url_replaces_a_missing_link_and_other_guids_do_not() -> None:
    body = rss(
        "<title>A</title><guid>https://example.com/g</guid>",
        "<title>B</title><guid isPermaLink='false'>abc-123</guid>",
    )
    articles, unreadable, _ = read_counted(body)

    assert [a.canonical_url for a in articles] == ["https://example.com/g"]
    assert unreadable == 1


def test_items_without_title_or_link_are_unreadable() -> None:
    body = rss(
        "<link>https://example.com/a</link>",
        "<title>No link</title>",
        item(link="https://example.com/ok"),
    )
    articles, unreadable, excluded = read_counted(body)

    assert ([a.canonical_url for a in articles], unreadable, excluded) == (
        ["https://example.com/ok"],
        2,
        0,
    )


def test_excerpt_is_plain_text_with_entities_decoded_even_when_escaped_twice() -> None:
    body = rss(
        item(description="&lt;p&gt;Fish &amp;amp; chips&lt;/p&gt; &lt;b&gt;now&lt;/b&gt;"),
        item(
            link="https://example.com/b",
            description="<![CDATA[<p>Caf&eacute; <i>au</i> lait</p>]]>",
        ),
    )
    first, second = read(body)

    assert first.excerpt == "Fish & chips now"
    assert second.excerpt == "Café au lait"


def test_content_encoded_is_preferred_when_longer_and_excerpt_is_capped() -> None:
    long_text = "word " * 1000
    short, longer = read(
        rss(
            item(description="Short summary", **{"content:encoded": "tiny"}),
            item(
                link="https://example.com/b",
                description="Short",
                **{"content:encoded": f"<p>{long_text}</p>"},
            ),
        )
    )

    assert short.excerpt == "Short summary"
    assert len(longer.excerpt) == 3000


def test_dates_are_made_plausible_and_old_items_are_dropped_whatever_the_order() -> None:
    body = rss(
        item(link="https://example.com/old", pubDate="Mon, 21 Sep 2026 05:00:00 GMT"),
        item(link="https://example.com/recent", pubDate="Tue, 20 Oct 2026 08:00:00 GMT"),
        item(link="https://example.com/future", pubDate="Wed, 21 Oct 2026 06:30:00 GMT"),
        item(link="https://example.com/soon", pubDate="Wed, 21 Oct 2026 06:10:00 GMT"),
        item(link="https://example.com/bad", pubDate="not a date"),
        item(link="https://example.com/none"),
        item(link="https://example.com/edge", pubDate="Wed, 23 Sep 2026 06:00:00 GMT"),
    )
    articles, unreadable, excluded = read_counted(body)
    dates = {a.canonical_url.rsplit("/", 1)[1]: a.published_at for a in articles}

    assert set(dates) == {"recent", "future", "soon", "bad", "none", "edge"}
    assert dates["recent"] == datetime(2026, 10, 20, 8, 0, tzinfo=UTC)
    assert dates["soon"] == datetime(2026, 10, 21, 6, 10, tzinfo=UTC)
    assert dates["future"] == dates["bad"] == dates["none"] == COLLECTED_AT
    assert (unreadable, excluded) == (0, 0)


def test_excluded_items_are_counted_apart_and_a_fully_excluded_feed_is_empty() -> None:
    body = rss(
        item(link="https://example.com/fiche_DN-1", description="x"),
        item(link="https://example.com/news", description="y"),
    )
    articles, unreadable, excluded = read_counted(body, "_DN-")
    assert ([a.canonical_url for a in articles], unreadable, excluded) == (
        ["https://example.com/news"],
        0,
        1,
    )

    assert read_counted(body, "_DN-", "news") == ([], 0, 2)


def test_patterns_are_matched_against_the_cleaned_url_and_are_case_sensitive() -> None:
    body = rss(item(link="/a_DN-1?utm_source=x#f", description="x"))

    assert read_counted(body, "utm_")[2] == 0
    assert read_counted(body, "_dn-")[2] == 0
    assert read_counted(body, "_DN-")[2] == 1


def test_a_republication_under_another_url_has_the_same_fingerprint() -> None:
    a, b = read(
        rss(
            item(link="https://example.com/a", description="<p>Same &amp; text</p>"),
            item(link="https://example.com/b?utm_source=x", description="Same &amp; text"),
        )
    )

    assert a.canonical_url != b.canonical_url
    assert a.fingerprint == b.fingerprint

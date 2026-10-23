"""Seam 2, purge side: `run_execution` with in-memory repositories."""

from datetime import timedelta

from nexus.core.ingestion.entities import (
    CollectionResult,
    Execution,
    ExecutionResult,
    PurgeTrace,
    RawArticle,
    SourceCollection,
)
from nexus.core.ingestion.normalization import to_article
from nexus.core.shared.ports import FetchError
from tests.unit.execution_harness import Harness, ok, rss_source

FEED = "https://a.example.com/feed"
DAY = timedelta(days=1)


def feed(*titles: str) -> bytes:
    items = "".join(
        f"<item><title>{title}</title><link>https://example.com/{title}</link>"
        f"<description>About {title}.</description></item>"
        for title in titles
    )
    return (
        f'<?xml version="1.0"?><rss version="2.0"><channel><title>E</title>{items}</channel></rss>'
    ).encode()


def stored(harness: Harness, title: str, age: timedelta) -> None:
    now = harness.clock.now()
    raw = RawArticle(
        title=title, link=f"https://example.com/{title}", text="Old.", published_at=None
    )
    harness.articles.rows.append(to_article(raw, 1, now - age))


async def test_expired_articles_are_purged_and_leave_a_trace() -> None:
    harness = Harness(rss_source(1, FEED), subscribed=[1])
    harness.serve(FEED, ok(feed()))
    stored(harness, "old", 31 * DAY)
    stored(harness, "recent", 29 * DAY)
    old = harness.articles.rows[0]

    report = await harness.run()

    assert [a.title for a in harness.articles.rows] == ["recent"]
    [trace] = harness.purge_traces.rows
    assert (trace.source_id, trace.canonical_url, trace.fingerprint) == (
        1,
        old.canonical_url,
        old.fingerprint,
    )
    assert trace.purged_at < report.execution.finished_at  # type: ignore[operator]


async def test_the_purge_runs_when_every_collection_failed() -> None:
    harness = Harness(rss_source(1, FEED), subscribed=[1])
    harness.serve(FEED, FetchError("timeout"))
    stored(harness, "old", 31 * DAY)

    report = await harness.run()

    assert report.execution.result is ExecutionResult.FAILED
    assert harness.articles.rows == []
    assert len(harness.purge_traces.rows) == 1


async def test_a_purged_article_still_in_the_feed_is_not_inserted_again() -> None:
    harness = Harness(rss_source(1, FEED), subscribed=[1])
    harness.serve(FEED, ok(feed("old")))
    stored(harness, "old", 31 * DAY)

    await harness.run()
    assert harness.articles.rows == []

    await harness.run()
    assert harness.articles.rows == []
    assert [c.article_count for c in harness.collections.rows] == [0, 0]


async def test_a_trace_matches_the_fingerprint_alone() -> None:
    harness = Harness(rss_source(1, FEED), subscribed=[1])
    harness.serve(FEED, ok(feed("old")))
    now = harness.clock.now()
    raw = RawArticle(
        title="old", link="https://elsewhere.example.com/old", text="About old.", published_at=None
    )
    harness.purge_traces.rows.append(
        PurgeTrace(1, "https://elsewhere.example.com/old", to_article(raw, 1, now).fingerprint, now)
    )

    await harness.run()

    assert harness.articles.rows == []


async def test_a_trace_of_another_source_does_not_block_insertion() -> None:
    harness = Harness(rss_source(1, FEED), subscribed=[1])
    harness.serve(FEED, ok(feed("old")))
    now = harness.clock.now()
    harness.purge_traces.rows.append(PurgeTrace(2, "https://example.com/old", "x", now))

    await harness.run()

    assert [a.title for a in harness.articles.rows] == ["old"]


async def test_old_traces_are_deleted_and_recent_ones_kept() -> None:
    harness = Harness()
    now = harness.clock.now()
    harness.purge_traces.rows.extend(
        [
            PurgeTrace(1, "https://example.com/a", "a", now - 366 * DAY),
            PurgeTrace(1, "https://example.com/b", "b", now - 364 * DAY),
        ]
    )

    await harness.run()

    assert [t.fingerprint for t in harness.purge_traces.rows] == ["b"]


async def test_old_executions_are_deleted_with_their_collections() -> None:
    harness = Harness()
    now = harness.clock.now()
    for id_, age in ((10, 91 * DAY), (11, 89 * DAY)):
        harness.executions.rows[id_] = Execution(id=id_, started_at=now - age)
        harness.collections.rows.append(
            SourceCollection(
                execution_id=id_,
                source_id=1,
                result=CollectionResult.SUCCESS,
                article_count=0,
                error_detail=None,
                started_at=now - age,
                finished_at=now - age,
            )
        )

    report = await harness.run()

    assert sorted(harness.executions.rows) == sorted([11, report.execution.id])
    assert [c.execution_id for c in harness.collections.rows] == [11]

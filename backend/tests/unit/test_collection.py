"""Seam 2, Collection side: `run_execution` with the real RSS Connector and a fake fetcher.

Every feed here is synthetic, written by hand.
"""

import asyncio

import pytest

from nexus.core.ingestion.entities import (
    AnomalyKind,
    CollectionResult,
    DeactivationReason,
    ExecutionResult,
    FailureCause,
)
from nexus.core.shared.ports import FetchError, FetchResponse, FetchUsage, HttpValidators
from tests.unit.execution_harness import Harness, ok, rss_source
from tests.unit.fakes import FakeHttpFetcher

FEED_A = "https://a.example.com/feed"
FEED_B = "https://b.example.com/feed"


def feed(*titles: str) -> bytes:
    items = "".join(
        f"<item><title>{title}</title><link>https://example.com/{title.replace(' ', '-')}</link>"
        f"<description>About {title}.</description></item>"
        for title in titles
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>E</title>'
        f"{items}</channel></rss>"
    ).encode()


async def test_subscribed_active_sources_are_collected_into_articles() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, ok(feed("One", "Two")))

    report = await harness.run()

    assert sorted(article.title for article in harness.articles.rows) == ["One", "Two"]
    [collection] = harness.collections.rows
    assert (collection.source_id, collection.result, collection.article_count) == (
        1,
        CollectionResult.SUCCESS,
        2,
    )
    assert collection.execution_id == report.execution.id
    assert harness.sources.rows["rss:a.example.com/feed"].last_collected_at is not None
    assert report.execution.result is ExecutionResult.SUCCESS
    assert report.execution.anomalies == ()


async def test_inactive_or_unsubscribed_sources_are_not_collected() -> None:
    harness = Harness(
        rss_source(1, FEED_A),
        rss_source(2, FEED_B, DeactivationReason.REPEATED_FAILURES),
        subscribed=[2],
    )

    report = await harness.run()

    assert harness.fetcher.requested == []
    assert harness.collections.rows == []
    [anomaly] = report.execution.anomalies
    assert anomaly.kind is AnomalyKind.NO_SOURCE_TO_COLLECT
    assert report.execution.result is ExecutionResult.SUCCESS


async def test_a_replayed_collection_inserts_no_duplicate() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, ok(feed("One", "Two")))

    await harness.run()
    await harness.run()

    assert len(harness.articles.rows) == 2
    assert [c.article_count for c in harness.collections.rows] == [2, 0]
    assert all(c.result is CollectionResult.SUCCESS for c in harness.collections.rows)


async def test_one_failed_collection_makes_the_execution_partial() -> None:
    harness = Harness(rss_source(1, FEED_A), rss_source(2, FEED_B), subscribed=[1, 2])
    harness.serve(FEED_A, ok(feed("One")))
    harness.serve(FEED_B, ok(b"", status=503))

    report = await harness.run()

    failed = next(c for c in harness.collections.rows if c.source_id == 2)
    assert failed.result is CollectionResult.FAILED
    assert failed.error_detail is not None
    assert "503" in failed.error_detail
    assert harness.sources.rows["rss:b.example.com/feed"].last_collected_at is None
    assert report.execution.result is ExecutionResult.PARTIAL


@pytest.mark.parametrize(
    ("response", "cause"),
    [
        (ok(b"", status=301), "301"),
        (ok(b"", status=429), "HTTP 429"),
        (ok(b"", status=503), "HTTP 503"),
        (FetchError("timeout after 30s"), "timeout"),
        (FetchError("only https URLs are fetched: http://a.example.com/feed"), "only https"),
        (ok(b'<?xml version="1.0"?><!DOCTYPE rss><rss/>'), "DOCTYPE"),
        (ok(b"<html><body>Not a feed</body></html>"), "not a feed"),
    ],
)
async def test_every_failed_collection_fails_the_execution_for_collection(
    response: object, cause: str
) -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, response)  # type: ignore[arg-type]

    report = await harness.run()

    [collection] = harness.collections.rows
    assert collection.result is CollectionResult.FAILED
    assert collection.article_count == 0
    assert cause in (collection.error_detail or "")
    assert harness.articles.rows == []
    assert report.execution.result is ExecutionResult.FAILED
    assert report.execution.failure_cause is FailureCause.COLLECTION


async def test_an_empty_feed_is_a_successful_collection() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, ok(feed()))

    report = await harness.run()

    [collection] = harness.collections.rows
    assert (collection.result, collection.article_count) == (CollectionResult.SUCCESS, 0)
    assert report.execution.result is ExecutionResult.SUCCESS


async def test_an_error_outside_collections_closes_the_execution_as_technical_failure() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, ok(feed("One")))

    async def broken(*args: object) -> None:
        raise RuntimeError("database gone")

    harness.sources.mark_collected = broken  # type: ignore[method-assign, assignment]

    with pytest.raises(RuntimeError, match="database gone"):
        await harness.run()

    [execution] = harness.executions.rows.values()
    assert execution.result is ExecutionResult.FAILED
    assert execution.failure_cause is FailureCause.TECHNICAL
    assert "database gone" in (execution.error_detail or "")
    assert harness.articles.rows == []
    assert harness.collections.rows == []


async def test_the_report_counts_unreadable_items_of_each_collection() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    untitled = b"<item><link>https://example.com/untitled</link></item>"
    harness.serve(FEED_A, ok(feed("One").replace(b"</channel>", untitled + b"</channel>")))

    report = await harness.run()

    [outcome] = report.collections
    assert (outcome.collection.article_count, outcome.unreadable_count) == (1, 1)
    assert outcome.excluded_count == 0


async def test_a_304_is_a_successful_collection_without_article_that_keeps_the_validators() -> None:
    validators = HttpValidators(etag='"v1"', last_modified="Mon, 01 Jan 2026")
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, ok(feed("One"), validators=validators))
    await harness.run()
    harness.serve(FEED_A, ok(b"", status=304))

    report = await harness.run()

    assert harness.fetcher.sent_validators[-1] == validators
    assert [(c.result, c.article_count) for c in harness.collections.rows] == [
        (CollectionResult.SUCCESS, 1),
        (CollectionResult.SUCCESS, 0),
    ]
    assert report.execution.result is ExecutionResult.SUCCESS
    assert harness.sources.rows["rss:a.example.com/feed"].validators == validators


async def test_validators_follow_each_200_and_are_cleared_when_the_server_stops_sending() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    key = "rss:a.example.com/feed"

    harness.serve(FEED_A, ok(feed("One"), validators=HttpValidators(etag='"v1"')))
    await harness.run()
    assert harness.sources.rows[key].validators == HttpValidators(etag='"v1"')

    harness.serve(FEED_A, ok(feed("One"), validators=HttpValidators(etag='"v2"')))
    await harness.run()
    assert harness.sources.rows[key].validators == HttpValidators(etag='"v2"')

    harness.serve(FEED_A, ok(feed("One")))
    await harness.run()
    assert harness.sources.rows[key].validators == HttpValidators()


async def test_a_failed_collection_leaves_the_validators_untouched() -> None:
    validators = HttpValidators(etag='"v1"')
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, ok(feed("One"), validators=validators))
    await harness.run()
    harness.serve(FEED_A, ok(b"", status=503))

    await harness.run()

    assert harness.sources.rows["rss:a.example.com/feed"].validators == validators


async def test_a_permanent_redirect_is_an_anomaly_with_the_old_and_the_new_url() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    new_url = "https://a.example.com/new-feed"
    harness.serve(FEED_A, ok(feed("One"), url=new_url, moved_permanently=True))

    report = await harness.run()

    [anomaly] = report.execution.anomalies
    assert anomaly.kind is AnomalyKind.FEED_MOVED
    assert FEED_A in anomaly.detail
    assert new_url in anomaly.detail
    assert report.execution.result is ExecutionResult.SUCCESS


async def test_a_temporary_redirect_is_not_an_anomaly() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, ok(feed("One"), url="https://a.example.com/tmp"))

    report = await harness.run()

    assert report.execution.anomalies == ()


async def test_at_most_eight_collections_run_at_the_same_time() -> None:
    class SlowFetcher(FakeHttpFetcher):
        running = 0
        peak = 0

        async def fetch(
            self, url: str, usage: FetchUsage, validators: HttpValidators | None = None
        ) -> FetchResponse:
            self.running += 1
            self.peak = max(self.peak, self.running)
            await asyncio.sleep(0.01)
            self.running -= 1
            return ok(feed())

    sources = [rss_source(i, f"https://s{i}.example.com/feed") for i in range(1, 21)]
    harness = Harness(*sources, subscribed=range(1, 21))
    slow = SlowFetcher()
    harness.fetcher = slow

    report = await harness.run()

    assert len(harness.collections.rows) == 20
    assert report.execution.result is ExecutionResult.SUCCESS
    assert slow.peak == 8

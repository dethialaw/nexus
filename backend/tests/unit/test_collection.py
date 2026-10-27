"""Seam 2, Collection side: `run_execution` with the real RSS Connector and a fake fetcher.

Every feed here is synthetic, written by hand.
"""

from dataclasses import replace

import pytest

from nexus.core.ingestion.entities import (
    AnomalyKind,
    CollectionResult,
    DeactivationReason,
    ExecutionResult,
    FailureCause,
)
from nexus.core.shared.ports import FetchError, FetchResponse, HttpValidators
from tests.unit.execution_harness import Harness, ok, rss_source

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


async def test_collection_stores_response_validators() -> None:
    source = rss_source(1, FEED_A)
    sent_validators = HttpValidators(etag='"v1"', last_modified="Mon, 01 Jan 2026")
    response_validators = HttpValidators(etag='"v2"', last_modified="Tue, 02 Jan 2026")
    harness = Harness(replace(source, validators=sent_validators), subscribed=[1])
    harness.serve(FEED_A, ok(feed("One"), validators=response_validators))

    await harness.run()

    assert harness.fetcher.sent_validators == [sent_validators]
    assert harness.sources.rows[source.source_key].validators == response_validators


async def test_not_modified_collection_preserves_missing_response_validators() -> None:
    source = rss_source(1, FEED_A)
    sent_validators = HttpValidators(etag='"v1"', last_modified="Mon, 01 Jan 2026")
    updated_validators = HttpValidators(etag='"v2"')
    harness = Harness(replace(source, validators=sent_validators), subscribed=[1])
    harness.serve(FEED_A, ok(b"", status=304, validators=updated_validators))

    await harness.run()

    assert harness.sources.rows[source.source_key].validators == HttpValidators(
        etag='"v2"', last_modified="Mon, 01 Jan 2026"
    )


@pytest.mark.parametrize(
    "response",
    [
        ok(feed("One"), url=FEED_B, moved_permanently=True),
        ok(b"", 304, FEED_B, moved_permanently=True),
    ],
)
async def test_a_permanent_redirect_is_an_anomaly_with_both_urls(response: FetchResponse) -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    harness.serve(FEED_A, response)

    report = await harness.run()

    assert report.execution.result is ExecutionResult.SUCCESS
    [anomaly] = report.execution.anomalies
    assert anomaly.kind is AnomalyKind.FEED_MOVED
    assert FEED_A in anomaly.detail
    assert FEED_B in anomaly.detail


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
    assert outcome.collection.unreadable_count == 1


async def fail_repeatedly(harness: Harness, times: int) -> None:
    harness.serve(FEED_A, FetchError("timeout"))
    for _ in range(times):
        await harness.run()


async def test_24_failed_collections_in_a_row_deactivate_the_source_with_an_anomaly() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    await fail_repeatedly(harness, 23)
    assert harness.sources.rows[rss_source(1, FEED_A).source_key].is_active

    report = await harness.run()

    source = harness.sources.rows[rss_source(1, FEED_A).source_key]
    assert source.deactivation_reason is DeactivationReason.REPEATED_FAILURES
    assert [a.kind for a in report.execution.anomalies] == [AnomalyKind.SOURCE_DEACTIVATED]
    assert source.source_key in report.execution.anomalies[0].detail


async def test_23_failures_then_a_success_deactivate_nothing() -> None:
    harness = Harness(rss_source(1, FEED_A), subscribed=[1])
    await fail_repeatedly(harness, 23)
    harness.serve(FEED_A, ok(feed("One")))
    await harness.run()
    harness.serve(FEED_A, FetchError("timeout"))

    report = await harness.run()

    assert harness.sources.rows[rss_source(1, FEED_A).source_key].is_active
    assert report.execution.anomalies == ()


async def test_catalog_sync_never_reactivates_a_source_deactivated_for_repeated_failures() -> None:
    harness = Harness(rss_source(1, FEED_A, DeactivationReason.REPEATED_FAILURES), subscribed=[1])

    await harness.run()

    source = harness.sources.rows[rss_source(1, FEED_A).source_key]
    assert source.deactivation_reason is DeactivationReason.REPEATED_FAILURES

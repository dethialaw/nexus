from itertools import count

import pytest
from pydantic import ValidationError

from nexus.core.ingestion.entities import AnomalyKind, Connector, DeactivationReason, Source
from nexus.core.ingestion.source_catalog import CatalogEntry, SourceCatalog, sync_source_catalog
from nexus.core.ingestion.source_config import RedditConfig

_ids = count(1)


def entry(name: str) -> CatalogEntry:
    return CatalogEntry(config=RedditConfig(subreddit=name))


def source(
    name: str, reason: DeactivationReason | None = None, owner_user_id: int | None = None
) -> Source:
    return Source(
        id=next(_ids),
        source_key=f"reddit:{name}",
        connector=Connector.REDDIT,
        config={"connector": "reddit", "subreddit": name},
        owner_user_id=owner_user_id,
        deactivation_reason=reason,
        last_collected_at=None,
    )


def catalog(*names: str, retired: tuple[str, ...] = ()) -> SourceCatalog:
    return SourceCatalog(
        sources=tuple(entry(name) for name in names),
        retired=tuple(f"reddit:{name}" for name in retired),
    )


def test_new_entries_are_inserted_and_known_ones_are_not() -> None:
    plan = sync_source_catalog(catalog("python", "rust"), [source("python")])

    assert [e.source_key for e in plan.to_insert] == ["reddit:rust"]
    assert plan.to_deactivate == ()
    assert plan.anomaly is None


def test_retired_key_deactivates_an_active_source() -> None:
    plan = sync_source_catalog(
        catalog("python", retired=("rust",)), [source("python"), source("rust")]
    )

    assert plan.to_deactivate == ("reddit:rust",)


def test_retired_key_leaves_an_inactive_source_alone() -> None:
    plan = sync_source_catalog(
        catalog("python", retired=("rust",)),
        [source("python"), source("rust", DeactivationReason.MAINTAINER)],
    )

    assert plan.to_deactivate == ()
    assert plan.to_reactivate == ()


def test_listing_again_does_not_reactivate_a_source_deactivated_for_another_reason() -> None:
    plan = sync_source_catalog(
        catalog("python", "rust"),
        [source("python"), source("rust", DeactivationReason.MAINTAINER)],
    )

    assert plan.to_reactivate == ()
    assert plan.to_insert == ()


def test_listing_again_reactivates_a_source_removed_from_catalog() -> None:
    plan = sync_source_catalog(
        catalog("python", "rust"),
        [source("python"), source("rust", DeactivationReason.REMOVED_FROM_CATALOG)],
    )

    assert plan.to_reactivate == ("reddit:rust",)


def test_unexplained_disappearances_below_threshold_are_deactivated() -> None:
    active = [source(f"s{i}") for i in range(10)]
    plan = sync_source_catalog(catalog(*(f"s{i}" for i in range(7))), active)

    assert plan.anomaly is None
    assert plan.to_deactivate == ("reddit:s7", "reddit:s8", "reddit:s9")


def test_more_than_three_disappearances_block_a_small_catalog() -> None:
    active = [source(f"s{i}") for i in range(10)]
    plan = sync_source_catalog(catalog(*(f"s{i}" for i in range(6)), "new"), active)

    assert plan.anomaly is not None
    assert plan.anomaly.kind is AnomalyKind.CATALOG_SYNC_BLOCKED
    assert plan.to_insert == ()
    assert plan.to_deactivate == plan.to_reactivate == ()


def test_threshold_is_twenty_percent_of_active_common_sources() -> None:
    active = [source(f"s{i}") for i in range(30)]

    six_missing = sync_source_catalog(catalog(*(f"s{i}" for i in range(24))), active)
    seven_missing = sync_source_catalog(catalog(*(f"s{i}" for i in range(23))), active)

    assert six_missing.anomaly is None
    assert seven_missing.anomaly is not None


def test_retirements_do_not_count_towards_the_threshold() -> None:
    active = [source(f"s{i}") for i in range(10)]
    plan = sync_source_catalog(
        catalog("s0", "s1", retired=tuple(f"s{i}" for i in range(2, 10))), active
    )

    assert plan.anomaly is None
    assert len(plan.to_deactivate) == 8


def test_empty_catalog_blocks_the_sync() -> None:
    plan = sync_source_catalog(catalog(), [source("python")])

    assert plan.anomaly is not None
    assert plan.to_deactivate == ()


def test_removing_an_inactive_key_from_retired_has_no_effect() -> None:
    plan = sync_source_catalog(
        catalog("python"),
        [source("python"), source("rust", DeactivationReason.REMOVED_FROM_CATALOG)],
    )

    assert plan == sync_source_catalog(catalog("python"), [source("python")])


def test_private_sources_are_ignored() -> None:
    plan = sync_source_catalog(
        catalog("python"), [source("python"), source("mine", owner_user_id=1)]
    )

    assert plan.to_deactivate == ()


@pytest.mark.parametrize(
    ("names", "retired"),
    [(("python", "Python"), ()), (("python",), ("python",)), (("python",), ("rust", "rust"))],
)
def test_catalog_rejects_duplicated_keys(names: tuple[str, ...], retired: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        catalog(*names, retired=retired)

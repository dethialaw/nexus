import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import AppUserRow, SourceRow, SubscriptionRow
from nexus.bootstrap import build_container
from nexus.entrypoints.admin.__main__ import run
from nexus.settings import Settings


@pytest.fixture
def admin(session_factory: async_sessionmaker[AsyncSession], database_url: str) -> "Admin":
    return Admin(database_url)


class Admin:
    def __init__(self, database_url: str) -> None:
        self._settings = Settings(database_url=SecretStr(database_url))

    async def __call__(self, *argv: str) -> int:
        return await run(list(argv), build_container(self._settings))


async def add_source(
    session_factory: async_sessionmaker[AsyncSession], name: str, *, active: bool = True
) -> None:
    async with session_factory() as session:
        session.add(
            SourceRow(
                source_key=f"reddit:{name}",
                connector="reddit",
                config={"connector": "reddit", "subreddit": name},
                is_active=active,
                deactivation_reason=None if active else "repeated_failures",
            )
        )
        await session.commit()


async def subscriptions(session_factory: async_sessionmaker[AsyncSession]) -> list[str]:
    async with session_factory() as session:
        rows = await session.execute(
            select(SourceRow.source_key).join(
                SubscriptionRow, SubscriptionRow.source_id == SourceRow.id
            )
        )
        return sorted(rows.scalars())


UPSERT = ("user", "upsert", "--handle", "maintainer")


async def test_user_upsert_is_idempotent_and_updates_timezone_and_hour(
    admin: "Admin", session_factory: async_sessionmaker[AsyncSession]
) -> None:
    first = await admin(*UPSERT, "--timezone", "Europe/Paris", "--briefing-hour", "7")
    second = await admin(*UPSERT, "--timezone", "Africa/Dakar", "--briefing-hour", "6")

    assert (first, second) == (0, 0)
    async with session_factory() as session:
        row = (await session.execute(select(AppUserRow))).scalar_one()
    assert (row.handle, row.timezone, row.briefing_hour) == ("maintainer", "Africa/Dakar", 6)


@pytest.mark.parametrize(
    ("handle", "timezone", "hour", "message"),
    [
        ("me@example.com", "Europe/Paris", "7", "handle"),
        ("maintainer", "Europe/Nowhere", "7", "timezone"),
        ("maintainer", "../etc/passwd", "7", "timezone"),
        ("maintainer", "Europe/Paris", "24", "hour"),
    ],
)
async def test_user_upsert_rejects_invalid_values(
    admin: "Admin",
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
    handle: str,
    timezone: str,
    hour: str,
    message: str,
) -> None:
    code = await admin(
        "user", "upsert", "--handle", handle, "--timezone", timezone, "--briefing-hour", hour
    )

    assert code != 0
    assert message in capsys.readouterr().err
    async with session_factory() as session:
        assert (await session.execute(select(AppUserRow))).first() is None


async def test_subscribe_and_unsubscribe_are_idempotent(
    admin: "Admin", session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await add_source(session_factory, "python")
    await admin(*UPSERT, "--timezone", "Europe/Paris", "--briefing-hour", "7")

    codes = [
        await admin("subscribe", "maintainer", "reddit:python"),
        await admin("subscribe", "maintainer", "reddit:python"),
    ]
    assert codes == [0, 0]
    assert await subscriptions(session_factory) == ["reddit:python"]

    codes = [
        await admin("unsubscribe", "maintainer", "reddit:python"),
        await admin("unsubscribe", "maintainer", "reddit:python"),
    ]
    assert codes == [0, 0]
    assert await subscriptions(session_factory) == []


async def test_subscriptions_are_additive(
    admin: "Admin", session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await add_source(session_factory, "python")
    await add_source(session_factory, "rust")
    await admin(*UPSERT, "--timezone", "Europe/Paris", "--briefing-hour", "7")

    await admin("subscribe", "maintainer", "reddit:python")
    await admin("subscribe", "maintainer", "reddit:rust")

    assert await subscriptions(session_factory) == ["reddit:python", "reddit:rust"]


async def test_subscribe_refuses_an_unknown_source_key(
    admin: "Admin",
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await admin(*UPSERT, "--timezone", "Europe/Paris", "--briefing-hour", "7")

    code = await admin("subscribe", "maintainer", "reddit:nope")

    assert code != 0
    assert "reddit:nope" in capsys.readouterr().err
    assert await subscriptions(session_factory) == []


async def test_subscribe_refuses_an_unknown_handle(
    admin: "Admin",
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await add_source(session_factory, "python")

    code = await admin("subscribe", "nobody", "reddit:python")

    assert code != 0
    assert "nobody" in capsys.readouterr().err


async def test_subscribe_to_an_inactive_source_warns_and_subscribes(
    admin: "Admin",
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await add_source(session_factory, "python", active=False)
    await admin(*UPSERT, "--timezone", "Europe/Paris", "--briefing-hour", "7")
    capsys.readouterr()

    code = await admin("subscribe", "maintainer", "reddit:python")

    assert code == 0
    assert "inactive" in capsys.readouterr().err
    assert await subscriptions(session_factory) == ["reddit:python"]

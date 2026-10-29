from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx2
import pytest

from nexus.bootstrap import build_feed_checker
from nexus.entrypoints.admin import __main__ as admin

FEED_URL = "https://example.com/feed.xml"


def rss(*items: str) -> bytes:
    return f"<rss version='2.0'><channel><title>t</title>{''.join(items)}</channel></rss>".encode()


def item(title: str, link: str, published_at: datetime) -> str:
    return (
        f"<item><title>{title}</title><link>{link}</link>"
        f"<pubDate>{format_datetime(published_at)}</pubDate></item>"
    )


@pytest.fixture
def no_database_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    for name in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(str(tmp_path))  # no `.env` to read


def serve(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    transport = httpx2.MockTransport(handler)  # type: ignore[arg-type]
    monkeypatch.setattr(
        admin, "build_feed_checker", lambda: build_feed_checker(transport=transport)
    )


@pytest.mark.usefixtures("no_database_configuration")
async def test_check_reports_items_validators_and_anomaly_without_any_database_setting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(UTC)
    body = rss(
        item("Kept", "https://example.com/a", now - timedelta(hours=1)),
        item("Dated", "https://example.com/_DN-b", now - timedelta(hours=2)),
        item("Old", "https://example.com/c", now - timedelta(days=60)),
        "<item><description>no title, no link</description></item>",
    )

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/feed.xml":
            return httpx2.Response(301, headers={"location": "https://example.com/new.xml"})
        return httpx2.Response(200, content=body, headers={"etag": '"v1"'})

    serve(monkeypatch, handler)

    code = await admin.run(["source", "check", FEED_URL, "--exclude-url-pattern", "_DN-"])

    out = capsys.readouterr().out
    assert code == 0
    assert "3 readable, 1 unreadable, 1 excluded" in out
    assert "[kept]" in out
    assert "[excluded]" in out
    assert "[too_old]" in out
    assert 'etag: "v1"' in out
    assert "anomaly feed_moved" in out


@pytest.mark.usefixtures("no_database_configuration")
async def test_check_shows_the_cause_of_a_refusal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    serve(monkeypatch, lambda request: httpx2.Response(200, content=b"<html></html>"))

    code = await admin.run(["source", "check", FEED_URL])

    assert code == 1
    assert "not a feed" in capsys.readouterr().err


@pytest.mark.usefixtures("no_database_configuration")
async def test_check_shows_the_new_url_when_parsing_fails_after_a_permanent_redirect(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/feed.xml":
            return httpx2.Response(301, headers={"location": "https://example.com/home"})
        return httpx2.Response(200, content=b"<html></html>")

    serve(monkeypatch, handler)

    code = await admin.run(["source", "check", FEED_URL])

    err = capsys.readouterr().err
    assert code == 1
    assert "not a feed" in err
    assert FEED_URL in err
    assert "https://example.com/home" in err


@pytest.mark.usefixtures("no_database_configuration")
async def test_check_refuses_an_http_url_without_any_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    serve(monkeypatch, lambda request: pytest.fail("no request expected"))

    code = await admin.run(["source", "check", "http://example.com/feed.xml"])

    assert code == 1
    assert "https" in capsys.readouterr().err

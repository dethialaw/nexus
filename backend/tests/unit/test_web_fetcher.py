"""Seam 3: the `HttpFetcher` adapter behind a simulated transport, without network."""

import asyncio

import httpx2
import pytest

from nexus.adapters.web.fetcher import WebFetcher
from nexus.core.shared.ports import BlockedByRobotsError, FetchError, FetchUsage, HttpValidators

FEED = "https://example.com/feed.xml"


def fetcher(handler: object, *, timeout: float = 0.05, max_bytes: int = 1024) -> WebFetcher:
    return WebFetcher(
        timeout_seconds=timeout,
        max_bytes=max_bytes,
        transport=httpx2.MockTransport(handler),  # type: ignore[arg-type]
    )


async def test_returns_status_body_and_final_url_and_identifies_nexus() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, content=b"<rss/>")

    response = await fetcher(handler).fetch(FEED, FetchUsage.FEED)

    assert (response.status, response.body, response.final_url) == (200, b"<rss/>", FEED)
    user_agent = seen[0].headers["user-agent"]
    assert "Nexus" in user_agent
    assert "github.com/dethialaw/nexus" in user_agent


async def test_an_http_url_is_refused_without_any_request() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("no request expected")

    with pytest.raises(FetchError, match="https"):
        await fetcher(handler).fetch("http://example.com/feed.xml", FetchUsage.FEED)


async def test_a_redirect_from_https_to_http_fails_the_fetch() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"location": "http://example.com/elsewhere"})

    with pytest.raises(FetchError, match="only https"):
        await fetcher(handler).fetch(FEED, FetchUsage.FEED)


async def test_a_permanent_redirect_is_followed_and_reported() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/feed.xml":
            return httpx2.Response(301, headers={"location": "/new.xml"})
        return httpx2.Response(200, content=b"<rss/>")

    response = await fetcher(handler).fetch(FEED, FetchUsage.FEED)

    assert response.status == 200
    assert response.final_url == "https://example.com/new.xml"
    assert response.moved_permanently


async def test_a_temporary_redirect_is_followed_without_being_reported() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/feed.xml":
            return httpx2.Response(302, headers={"location": "https://cdn.example.net/other.xml"})
        return httpx2.Response(200, content=b"<rss/>")

    response = await fetcher(handler).fetch(FEED, FetchUsage.FEED)

    assert response.final_url == "https://cdn.example.net/other.xml"
    assert not response.moved_permanently


async def test_a_redirect_loop_fails_the_fetch() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"location": FEED})

    with pytest.raises(FetchError, match="redirects"):
        await fetcher(handler).fetch(FEED, FetchUsage.FEED)


async def test_validators_are_sent_and_the_new_ones_returned() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200, content=b"<rss/>", headers={"etag": '"v2"', "last-modified": "Tue, 02 Jan 2026"}
        )

    response = await fetcher(handler).fetch(
        FEED, FetchUsage.FEED, HttpValidators(etag='"v1"', last_modified="Mon, 01 Jan 2026")
    )

    assert seen[0].headers["if-none-match"] == '"v1"'
    assert seen[0].headers["if-modified-since"] == "Mon, 01 Jan 2026"
    assert response.validators == HttpValidators('"v2"', "Tue, 02 Jan 2026")


async def test_no_validators_are_sent_without_any_and_a_304_is_returned() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(304)

    response = await fetcher(handler).fetch(FEED, FetchUsage.FEED)

    assert response.status == 304
    assert "if-none-match" not in seen[0].headers
    assert "if-modified-since" not in seen[0].headers
    assert response.validators == HttpValidators()


async def test_a_feed_ignores_robots_txt() -> None:
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        return httpx2.Response(200, content=b"<rss/>")

    await fetcher(handler).fetch(FEED, FetchUsage.FEED)

    assert paths == ["/feed.xml"]


async def test_a_linked_page_is_refused_when_robots_txt_forbids_it() -> None:
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        return httpx2.Response(200, content=b"User-agent: *\nDisallow: /private/")

    with pytest.raises(BlockedByRobotsError):
        await fetcher(handler).fetch("https://example.com/private/a", FetchUsage.LINKED_PAGE)

    assert paths == ["/robots.txt"]


async def test_a_linked_page_is_fetched_when_robots_txt_allows_it() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/robots.txt":
            return httpx2.Response(200, content=b"User-agent: *\nDisallow: /private/")
        return httpx2.Response(200, content=b"<html/>")

    response = await fetcher(handler).fetch("https://example.com/public/a", FetchUsage.AGENT_PAGE)

    assert response.body == b"<html/>"


@pytest.mark.parametrize(("status", "allowed"), [(404, True), (403, False), (503, False)])
async def test_a_missing_or_unreadable_robots_txt(status: int, allowed: bool) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/robots.txt":
            return httpx2.Response(status)
        return httpx2.Response(200, content=b"<html/>")

    fetch = fetcher(handler).fetch("https://example.com/a", FetchUsage.LINKED_PAGE)

    if allowed:
        assert (await fetch).status == 200
    else:
        with pytest.raises(BlockedByRobotsError):
            await fetch


async def test_one_request_at_a_time_per_domain_but_domains_run_together() -> None:
    running: dict[str, int] = {}
    peak: dict[str, int] = {}

    async def handler(request: httpx2.Request) -> httpx2.Response:
        host = request.url.host
        running[host] = running.get(host, 0) + 1
        peak[host] = max(peak.get(host, 0), running[host])
        await asyncio.sleep(0.01)
        running[host] -= 1
        return httpx2.Response(200, content=b"<rss/>")

    web = fetcher(handler, timeout=1)
    urls = [f"https://{host}/{i}" for host in ("a.example", "b.example") for i in range(3)]
    await asyncio.gather(*(web.fetch(url, FetchUsage.FEED) for url in urls))

    assert peak == {"a.example": 1, "b.example": 1}


async def test_two_domains_are_fetched_at_the_same_time() -> None:
    both_started = asyncio.Event()
    started = 0

    async def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        return httpx2.Response(200, content=b"<rss/>")

    web = fetcher(handler, timeout=2)
    await asyncio.gather(
        web.fetch("https://a.example/x", FetchUsage.FEED),
        web.fetch("https://b.example/x", FetchUsage.FEED),
    )


async def test_a_slow_response_times_out() -> None:
    async def handler(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(1)
        return httpx2.Response(200, content=b"<rss/>")

    with pytest.raises(FetchError, match="timeout"):
        await fetcher(handler, timeout=0.05).fetch(FEED, FetchUsage.FEED)


async def test_a_response_larger_than_the_limit_is_refused() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"x" * 2048)

    with pytest.raises(FetchError, match="larger than 1024 bytes"):
        await fetcher(handler, max_bytes=1024).fetch(FEED, FetchUsage.FEED)


async def test_a_network_error_is_a_fetch_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    with pytest.raises(FetchError, match="network error"):
        await fetcher(handler).fetch(FEED, FetchUsage.FEED)

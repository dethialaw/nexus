"""Seam 3: the `HttpFetcher` adapter behind a simulated transport, without network."""

import asyncio

import httpx2
import pytest

from nexus.adapters.web.fetcher import WebFetcher
from nexus.core.shared.ports import FetchError, FetchUsage

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


async def test_a_redirect_is_not_followed() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(301, headers={"location": "http://example.com/elsewhere"})

    response = await fetcher(handler).fetch(FEED, FetchUsage.FEED)

    assert response.status == 301


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


async def test_usages_other_than_feeds_are_refused_until_robots_txt_is_applied() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("no request expected")

    with pytest.raises(FetchError, match=r"robots\.txt"):
        await fetcher(handler).fetch("https://example.com/page", FetchUsage.LINKED_PAGE)

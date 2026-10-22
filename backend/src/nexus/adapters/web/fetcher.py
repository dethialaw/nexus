"""`HttpFetcher` over httpx2: HTTPS only, identified, bounded in time and size."""

import asyncio
from urllib.parse import urlsplit

import httpx2

from nexus.core.shared.ports import FetchError, FetchResponse, FetchUsage

USER_AGENT = "Nexus/0.1 (personal news watch; +https://github.com/dethialaw/nexus)"


class WebFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_bytes: int,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._transport = transport

    async def fetch(self, url: str, usage: FetchUsage) -> FetchResponse:
        if urlsplit(url).scheme != "https":
            raise FetchError(f"only https URLs are fetched: {url}")
        if usage is not FetchUsage.FEED:
            # robots.txt applies to every usage but feeds; it comes with Linked pages.
            raise FetchError(f"{usage} fetches wait for robots.txt support")
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._get(url)
        except TimeoutError as error:
            raise FetchError(f"timeout after {self._timeout_seconds}s") from error
        except httpx2.HTTPError as error:
            raise FetchError(f"network error: {type(error).__name__}: {error}") from error

    async def _get(self, url: str) -> FetchResponse:
        # Redirects are not followed: each hop must be checked against the HTTPS rule first.
        async with (
            httpx2.AsyncClient(
                transport=self._transport,
                follow_redirects=False,
                headers={"user-agent": USER_AGENT},
                timeout=self._timeout_seconds,
            ) as client,
            client.stream("GET", url) as response,
        ):
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > self._max_bytes:
                    raise FetchError(f"response larger than {self._max_bytes} bytes")
            return FetchResponse(
                status=response.status_code, body=bytes(body), final_url=str(response.url)
            )

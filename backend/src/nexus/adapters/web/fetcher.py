"""`HttpFetcher` over httpx2: HTTPS only, polite, identified, bounded in time and size."""

import asyncio
from collections import defaultdict
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx2

from nexus.core.shared.ports import (
    BlockedByRobotsError,
    FetchError,
    FetchResponse,
    FetchUsage,
    HttpValidators,
)

USER_AGENT = "Nexus/0.1 (personal news watch; +https://github.com/dethialaw/nexus)"
ROBOTS_AGENT = "Nexus"
MAX_REDIRECTS = 5
PERMANENT_REDIRECTS = frozenset({301, 308})
REDIRECTS = frozenset({301, 302, 303, 307, 308})


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
        self._domain_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._robots: dict[str, RobotFileParser] = {}

    async def fetch(
        self, url: str, usage: FetchUsage, validators: HttpValidators | None = None
    ) -> FetchResponse:
        _require_https(url)
        try:
            if usage is not FetchUsage.FEED:
                # Feeds are published for machines; every other usage obeys robots.txt.
                await self._check_robots(url)
            return await self._get(url, validators or HttpValidators())
        except TimeoutError as error:
            raise FetchError(f"timeout after {self._timeout_seconds}s") from error
        except httpx2.HTTPError as error:
            raise FetchError(f"network error: {type(error).__name__}: {error}") from error

    async def _get(self, url: str, validators: HttpValidators) -> FetchResponse:
        # Redirects are followed by hand: each hop must be checked against the HTTPS rule first.
        headers = {"user-agent": USER_AGENT}
        if validators.etag:
            headers["if-none-match"] = validators.etag
        if validators.last_modified:
            headers["if-modified-since"] = validators.last_modified
        current = url
        moved = False
        for _ in range(MAX_REDIRECTS + 1):
            status, response_headers, body = await self._request(current, headers)
            location = response_headers.get("location")
            if status not in REDIRECTS or location is None:
                return FetchResponse(
                    status=status,
                    body=body,
                    final_url=current,
                    validators=HttpValidators(
                        etag=response_headers.get("etag"),
                        last_modified=response_headers.get("last-modified"),
                    ),
                    moved_permanently=moved,
                )
            moved = moved or status in PERMANENT_REDIRECTS
            current = urljoin(current, location)
            _require_https(current, redirected_from=url)
        raise FetchError(f"more than {MAX_REDIRECTS} redirects from {url}")

    async def _request(
        self, url: str, headers: dict[str, str]
    ) -> tuple[int, httpx2.Headers, bytes]:
        """One request, alone on its domain; the time limit starts once the domain is free."""
        async with (
            self._domain_locks[urlsplit(url).netloc.lower()],
            asyncio.timeout(self._timeout_seconds),
            httpx2.AsyncClient(
                transport=self._transport,
                follow_redirects=False,
                headers=headers,
                timeout=self._timeout_seconds,
            ) as client,
            client.stream("GET", url) as response,
        ):
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > self._max_bytes:
                    raise FetchError(f"response larger than {self._max_bytes} bytes")
            return response.status_code, response.headers, bytes(body)

    async def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc.lower()}"
        parser = self._robots.get(origin)
        if parser is None:
            parser = await self._read_robots(origin)
            self._robots[origin] = parser
        if not parser.can_fetch(ROBOTS_AGENT, url):
            raise BlockedByRobotsError(f"robots.txt of {origin} forbids {url}")

    async def _read_robots(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        disallow_all = ["User-agent: *", "Disallow: /"]
        try:
            response = await self._get(f"{origin}/robots.txt", HttpValidators())
        except (FetchError, httpx2.HTTPError, TimeoutError):
            # robots.txt cannot be read: assume the worst, as crawlers do on a server error.
            parser.parse(disallow_all)
            return parser
        if response.status in (401, 403) or response.status >= 500:
            parser.parse(disallow_all)
        elif response.status == 200:
            parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
        else:
            parser.parse([])
        return parser


def _require_https(url: str, *, redirected_from: str | None = None) -> None:
    if urlsplit(url).scheme != "https":
        origin = "" if redirected_from is None else f" (redirect from {redirected_from})"
        raise FetchError(f"only https URLs are fetched: {url}{origin}")

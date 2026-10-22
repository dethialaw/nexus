"""Pre-filter run on the bytes of any collected XML, before any parser (backend/AGENTS.md).

feedparser never resolves external entities, but its own DOCTYPE filter is bypassed by a comment
placed before it; only expat's amplification limit would then stand against billion laughs.
"""

import re

from nexus.core.ingestion.errors import CollectionError

_WIDE_PREFIXES = (
    # Byte order marks, UTF-32 before UTF-16: the UTF-32 LE mark starts with the UTF-16 LE one.
    (b"\xff\xfe\x00\x00", "UTF-32"),
    (b"\x00\x00\xfe\xff", "UTF-32"),
    (b"\xff\xfe", "UTF-16"),
    (b"\xfe\xff", "UTF-16"),
    # "<?" without a mark (XML 1.0, appendix F).
    (b"\x3c\x00\x00\x00", "UTF-32"),
    (b"\x00\x00\x00\x3c", "UTF-32"),
    (b"\x3c\x00\x3f\x00", "UTF-16"),
    (b"\x00\x3c\x00\x3f", "UTF-16"),
)
_DECLARED_WIDE = re.compile(
    rb"\A(?:\xef\xbb\xbf)?\s*<\?xml[^>]*?encoding\s*=\s*[\"']\s*(utf-?16|ucs-?2|utf-?32|ucs-?4)",
    re.IGNORECASE,
)
_DECLARATION = re.compile(rb"<!\s*(doctype|entity)", re.IGNORECASE)


def check_xml(body: bytes) -> None:
    """Raise `CollectionError` for a wide encoding or any DOCTYPE or ENTITY declaration."""
    for prefix, encoding in _WIDE_PREFIXES:
        if body.startswith(prefix):
            raise CollectionError(f"refused before parsing: {encoding} document")
    declared = _DECLARED_WIDE.match(body)
    if declared:
        encoding = "UTF-32" if declared.group(1).lower().endswith((b"32", b"4")) else "UTF-16"
        raise CollectionError(f"refused before parsing: {encoding} document")
    found = _DECLARATION.search(body)
    if found:
        kind = found.group(1).decode().upper()
        raise CollectionError(f"refused before parsing: {kind} declaration")

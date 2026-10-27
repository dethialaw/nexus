"""Pre-filter run on the bytes of any collected XML, before any parser (backend/AGENTS.md).

feedparser never resolves external entities, but its own DOCTYPE filter is bypassed by a comment
placed before it; only expat's amplification limit would then stand against billion laughs.
"""

import codecs
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
    # "<?xm" in EBCDIC, which feedparser then decodes as cp037.
    (b"\x4c\x6f\xa7\x94", "cp037"),
)
_UTF_BOM = b"\xef\xbb\xbf"
_WIDE_NAME = re.compile(r"utf-?(16|32)|ucs-?(2|4)", re.IGNORECASE)
# The declaration, however spaced, and feedparser's own reading of the first line: it takes
# the encoding of any leading processing instruction, not only `<?xml`.
_DECLARED = re.compile(rb"\A\s*<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']*)", re.IGNORECASE)
_FEEDPARSER_DECLARED = re.compile(rb"^<\?.*encoding=['\"](.*?)['\"].*\?>")
# Encodings where every ASCII character keeps its single ASCII byte, so a declaration found
# in the decoded text is also found in the raw bytes.
_ASCII_COMPATIBLE = frozenset(
    codecs.lookup(name).name
    for name in (
        "ascii",
        "utf-8",
        *(f"iso-8859-{n}" for n in (*range(1, 12), *range(13, 17))),
        *(f"windows-{n}" for n in range(1250, 1259)),
    )
)
_DECLARATION = re.compile(rb"<!\s*(doctype|entity)", re.IGNORECASE)


def check_xml(body: bytes) -> None:
    """Raise `CollectionError` for an encoding that is not ASCII-compatible, or for any DOCTYPE
    or ENTITY declaration."""
    for prefix, encoding in _WIDE_PREFIXES:
        if body.startswith(prefix):
            raise CollectionError(f"refused before parsing: {encoding} document")
    unmarked = body.removeprefix(_UTF_BOM)
    for pattern in (_DECLARED, _FEEDPARSER_DECLARED):
        declared = pattern.match(unmarked)
        if declared:
            _check_declared_encoding(declared.group(1).decode("ascii", errors="replace").strip())
    found = _DECLARATION.search(body)
    if found:
        kind = found.group(1).decode().upper()
        raise CollectionError(f"refused before parsing: {kind} declaration")


def _check_declared_encoding(name: str) -> None:
    wide = _WIDE_NAME.fullmatch(name)
    if wide:
        encoding = "UTF-16" if wide.group(1) == "16" or wide.group(2) == "2" else "UTF-32"
        raise CollectionError(f"refused before parsing: {encoding} document")
    try:
        canonical = codecs.lookup(name).name
    except LookupError:
        canonical = None
    if canonical not in _ASCII_COMPATIBLE:
        raise CollectionError(f"refused before parsing: {name} encoding is not ASCII-compatible")

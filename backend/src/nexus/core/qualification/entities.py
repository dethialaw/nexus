"""Qualification: Nature of an Article and same-event judgments."""

from enum import StrEnum


class Nature(StrEnum):
    OFFICIAL = "official"
    FACTUAL = "factual"
    RUMOR = "rumor"
    OPINION = "opinion"
    UNKNOWN = "unknown"

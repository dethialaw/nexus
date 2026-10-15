"""Delivery: Compositions, Briefings and Entries."""

from enum import StrEnum


class BriefingStatus(StrEnum):
    NORMAL = "normal"
    PARTIAL = "partial"
    FAILED = "failed"


class CompositionResult(StrEnum):
    NORMAL = "normal"
    PARTIAL = "partial"
    FAILED = "failed"

"""Errors of the ingestion section."""

from nexus.core.shared.errors import NexusError


class CollectionError(NexusError):
    """A Collection fails: the message is its recorded cause."""

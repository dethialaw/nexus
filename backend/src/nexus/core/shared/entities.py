"""Value types shared by every core section."""

from dataclasses import dataclass
from enum import StrEnum

EMBEDDING_DIMENSIONS = 768


class EmbeddingKind(StrEnum):
    DOCUMENT = "document"
    QUERY = "query"


@dataclass(frozen=True, slots=True)
class Embedding:
    """A vector with the model that produced it. Two models are never compared (ADR-0004)."""

    vector: tuple[float, ...]
    model: str
    kind: EmbeddingKind

    def __post_init__(self) -> None:
        if len(self.vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"embedding must have {EMBEDDING_DIMENSIONS} dimensions, got {len(self.vector)}"
            )

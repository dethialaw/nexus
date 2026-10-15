"""Conversation: messages exchanged with the agent and their Citations."""

from enum import StrEnum


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class CitationKind(StrEnum):
    ARTICLE = "article"
    FOLLOWED_PAGE = "followed_page"

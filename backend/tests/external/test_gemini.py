"""ADR-0004: `gemini-embedding-2` gives normalized 768-dimension vectors.

The model takes no `task_type`: document and query are told apart by a prefix in the text.
"""

import math

import httpx2
import pytest
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from tests.integration.conftest import BACKEND_DIR

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-2:embedContent"


class GeminiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    gemini_api_key: SecretStr


@pytest.mark.parametrize(
    "prompt",
    [
        "title: Python 3.14 released | text: The new release ships free-threading by default.",
        "task: search result | query: what is new in Python async?",
    ],
    ids=["document", "query"],
)
def test_embedding_has_768_dimensions_and_unit_norm(prompt: str) -> None:
    response = httpx2.post(
        ENDPOINT,
        headers={"x-goog-api-key": GeminiSettings().gemini_api_key.get_secret_value()},
        json={
            "model": "models/gemini-embedding-2",
            "content": {"parts": [{"text": prompt}]},
            "output_dimensionality": 768,
        },
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    embedding = body["embedding"] if "embedding" in body else body["embeddings"][0]
    values = [float(v) for v in embedding["values"]]

    assert len(values) == 768
    assert math.sqrt(sum(v * v for v in values)) == pytest.approx(1.0, abs=1e-3)

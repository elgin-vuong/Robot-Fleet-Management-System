"""Embeddings provider abstraction.

This is the only file in the codebase that imports the `voyageai` SDK.
Everything else (the /documents ingestion route, the search_documents tool)
talks to `EmbeddingsClient`, so swapping providers later means changing this
one file.

Configuration is via environment variables only:
    VOYAGE_API_KEY - required to actually call the provider
    VOYAGE_MODEL   - optional, defaults to DEFAULT_MODEL

No key is ever hard-coded, logged, or included in error messages sent to
clients.
"""

import os
from typing import Literal

import voyageai

from backend.app.agent.exceptions import EmbeddingProviderError

DEFAULT_MODEL = "voyage-3.5-lite"
EMBEDDING_DIM = 1024


class EmbeddingsClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("VOYAGE_API_KEY")
        self.model = model or os.getenv("VOYAGE_MODEL", DEFAULT_MODEL)

        if not self.api_key:
            raise EmbeddingProviderError(
                "VOYAGE_API_KEY is not configured. Set the VOYAGE_API_KEY environment "
                "variable to enable document ingestion and semantic search."
            )

        self._client = voyageai.Client(api_key=self.api_key)

    def embed(
        self, texts: list[str], *, input_type: Literal["document", "query"]
    ) -> list[list[float]]:
        try:
            result = self._client.embed(
                texts,
                model=self.model,
                input_type=input_type,
                output_dimension=EMBEDDING_DIM,
            )
        except Exception as exc:
            raise EmbeddingProviderError(f"Embeddings request failed: {exc}") from exc

        return result.embeddings

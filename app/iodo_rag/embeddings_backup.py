from __future__ import annotations

import os
from typing import Iterable

import requests


class EmbeddingClient:
    def __init__(self, base_url: str, expected_dim: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.expected_dim = expected_dim
        self.batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "8"))

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        inputs = [text for text in texts]
        if not inputs:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(inputs), self.batch_size):
            vectors.extend(self._embed_batch(inputs[start : start + self.batch_size]))

        return vectors

    def _embed_batch(self, inputs: list[str]) -> list[list[float]]:
        response = requests.post(
            f"{self.base_url}/embed",
            json={"inputs": inputs},
            timeout=120,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}; TEI response: {response.text[:1000]}",
                response=response,
            ) from exc

        vectors = response.json()

        if not isinstance(vectors, list):
            raise ValueError(f"Unexpected embedding response: {vectors!r}")

        for vector in vectors:
            if len(vector) != self.expected_dim:
                raise ValueError(
                    f"Embedding dimension mismatch: got {len(vector)}, expected {self.expected_dim}"
                )
        return vectors

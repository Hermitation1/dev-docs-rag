"""Embedding port and its implementations."""

import math
import re
import zlib
from collections.abc import Sequence
from typing import Protocol

_WORD_RE = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    """Turns text into vectors of a fixed size."""

    model_name: str
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of documents that will be indexed."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        ...


class FastEmbedEmbedder:
    """Local ONNX embeddings through fastembed, loaded once per process."""

    def __init__(self, model_name: str, dim: int, batch_size: int = 32) -> None:
        """Load the model lazily so tests never download weights."""
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.dim = dim
        self._batch_size = batch_size
        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed documents in batches."""
        if not texts:
            return []
        return [
            vector.tolist()
            for vector in self._model.embed(list(texts), batch_size=self._batch_size)
        ]

    def embed_query(self, text: str) -> list[float]:
        """Embed one query string."""
        return self.embed_documents([text])[0]


class FakeEmbedder:
    """Deterministic bag-of-words embeddings for tests.

    Texts that share words get similar vectors, so search tests can assert that a
    query finds the chunk it is supposed to find without loading a real model.
    """

    def __init__(self, dim: int = 384, model_name: str = "fake-bow") -> None:
        """Remember the vector size and the name reported to the database."""
        self.dim = dim
        self.model_name = model_name

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed each text independently."""
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Embed a query the same way as a document."""
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in _WORD_RE.findall(text.lower()):
            vector[zlib.crc32(word.encode("utf-8")) % self.dim] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]

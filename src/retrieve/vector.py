"""Dense vector retriever backed by `src.index.qdrant_store.QdrantStore`.

This is the T0 baseline every later week (BM25 at T2, hybrid+rerank at T4,
metadata filter at T5) is measured against.
"""

from __future__ import annotations

from qdrant_client.http import models as qm

from src.index.qdrant_store import QdrantStore
from src.providers.base import EmbeddingProvider
from src.retrieve.base import SearchHit, dedupe_by_doc


class VectorRetriever:
    """Embeds the query, then does an ANN lookup in Qdrant."""

    def __init__(
        self,
        store: QdrantStore,
        embedder: EmbeddingProvider,
        *,
        oversample: int = 3,
    ) -> None:
        self._store = store
        self._embedder = embedder
        # Fetch more than k before collapsing passages to documents, otherwise
        # several chunks of one article can crowd out other documents.
        self._oversample = max(1, oversample)

    @property
    def name(self) -> str:
        return f"vector[{self._embedder.model}@{self._embedder.dim}]"

    def retrieve(self, query: str, k: int) -> list[SearchHit]:
        return self.retrieve_filtered(query, k, None)

    def retrieve_filtered(
        self, query: str, k: int, query_filter: qm.Filter | None
    ) -> list[SearchHit]:
        # RETRIEVAL_QUERY vs RETRIEVAL_DOCUMENT: asymmetric encoding, which is
        # why task_type is part of the EmbeddingProvider contract.
        vector = self._embedder.embed([query], task_type="RETRIEVAL_QUERY")[0]
        points = self._store.search(vector, k * self._oversample, query_filter=query_filter)

        hits = []
        for point in points:
            payload = point.payload or {}
            doc_id = payload.get("doc_id")
            if not doc_id:
                continue
            hits.append(
                SearchHit(
                    doc_id=str(doc_id),
                    score=float(point.score),
                    passage_id=payload.get("passage_id"),
                    title=payload.get("title"),
                    text=payload.get("text"),
                    metadata={
                        key: payload.get(key)
                        for key in (
                            "doc_type",
                            "doc_type_label",
                            "year",
                            "issuer",
                            "article_no",
                            "khoan_no",
                        )
                    },
                )
            )
        return dedupe_by_doc(hits, k)

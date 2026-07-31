"""Qdrant collection wrapper — named dense vector, deterministic point ids.

Design notes:

* The collection uses a **named** dense vector (``"dense"``) from the start.
  Qdrant cannot add a new named vector to an existing collection, so naming it
  now keeps a future sparse-vector addition (hybrid search) a re-index rather
  than a rewrite.
* Point ids must be uint64 or UUID, but our natural key is a string like
  ``01/2009/tt-bnn+1``. We derive a deterministic UUID5 from it, so re-running
  the indexer upserts in place instead of duplicating.
* Payload indexes are created up front for the fields T5 will filter on, even
  though nothing filters yet.
"""

from __future__ import annotations

import logging
import uuid
import warnings
from collections.abc import Iterable, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from config.settings import Settings
from src.schemas import Passage

logger = logging.getLogger(__name__)

DENSE_VECTOR = "dense"

# Namespace for deriving stable point ids from passage ids.
_ID_NAMESPACE = uuid.UUID("6f6a1d2c-6b1e-4c9f-9f1a-2d3b4c5d6e7f")

# Fields that become metadata filters in T5.
_INDEXED_PAYLOAD_FIELDS: dict[str, qm.PayloadSchemaType] = {
    "doc_id": qm.PayloadSchemaType.KEYWORD,
    "doc_key": qm.PayloadSchemaType.KEYWORD,
    "doc_type": qm.PayloadSchemaType.KEYWORD,
    "issuer": qm.PayloadSchemaType.KEYWORD,
    "year": qm.PayloadSchemaType.INTEGER,
}


def point_id(passage_id: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, passage_id))


class QdrantStore:
    def __init__(self, settings: Settings, client: QdrantClient | None = None) -> None:
        self._settings = settings
        self._collection = settings.collection_name
        self._client = client or QdrantClient(url=settings.qdrant_url, timeout=60)

    @property
    def collection(self) -> str:
        return self._collection

    @property
    def client(self) -> QdrantClient:
        return self._client

    def ensure_collection(self, *, recreate: bool = False) -> None:
        exists = self._client.collection_exists(self._collection)
        if exists and recreate:
            logger.info("Dropping collection %s", self._collection)
            self._client.delete_collection(self._collection)
            exists = False
        if not exists:
            logger.info(
                "Creating collection %s (dim=%d, cosine)",
                self._collection,
                self._settings.embed_dim,
            )
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config={
                    DENSE_VECTOR: qm.VectorParams(
                        size=self._settings.embed_dim,
                        distance=qm.Distance.COSINE,
                    )
                },
            )
        for field, schema in _INDEXED_PAYLOAD_FIELDS.items():
            try:
                with warnings.catch_warnings():
                    # In-memory Qdrant (used by tests) ignores payload indexes and
                    # says so loudly; the call is still correct against a server.
                    warnings.filterwarnings(
                        "ignore", message=".*Payload indexes have no effect.*"
                    )
                    self._client.create_payload_index(
                        collection_name=self._collection,
                        field_name=field,
                        field_schema=schema,
                    )
            except Exception:  # noqa: BLE001 - index already present is not an error
                logger.debug("Payload index %s already present", field)

    def upsert(self, passages: Sequence[Passage], vectors: Sequence[Sequence[float]]) -> int:
        if len(passages) != len(vectors):
            raise ValueError(
                f"Got {len(passages)} passages but {len(vectors)} vectors — "
                "embeddings must align positionally with passages."
            )
        if not passages:
            return 0

        points = [
            qm.PointStruct(
                id=point_id(passage.passage_id),
                vector={DENSE_VECTOR: list(vector)},
                payload={
                    "passage_id": passage.passage_id,
                    "doc_id": passage.doc_id,
                    "title": passage.title,
                    "text": passage.text,
                    "doc_key": passage.metadata.doc_key,
                    "doc_type": passage.metadata.doc_type,
                    "doc_type_label": passage.metadata.doc_type_label,
                    "issuer": passage.metadata.issuer,
                    "year": passage.metadata.year,
                    "article_no": passage.metadata.article_no,
                    "khoan_no": passage.metadata.khoan_no,
                },
            )
            for passage, vector in zip(passages, vectors, strict=True)
        ]
        self._client.upsert(collection_name=self._collection, points=points, wait=True)
        return len(points)

    def search(
        self,
        vector: Sequence[float],
        k: int,
        query_filter: qm.Filter | None = None,
    ) -> list[qm.ScoredPoint]:
        response = self._client.query_points(
            collection_name=self._collection,
            query=list(vector),
            using=DENSE_VECTOR,
            limit=k,
            query_filter=query_filter,
            with_payload=True,
        )
        return list(response.points)

    def count(self) -> int:
        return self._client.count(collection_name=self._collection, exact=True).count

    def collection_info(self) -> dict[str, object]:
        info = self._client.get_collection(self._collection)
        return {
            "collection": self._collection,
            "points": info.points_count,
            "status": str(info.status),
        }

    def iter_payloads(self, batch: int = 256) -> Iterable[dict]:
        """Scroll every payload — used to build a lexical (BM25) index in T2."""
        offset = None
        while True:
            records, offset = self._client.scroll(
                collection_name=self._collection,
                limit=batch,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                yield record.payload or {}
            if offset is None:
                return

# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""RAG retriever — vector store backed retrieval for code patterns and rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from sw360_review_agent.config import VectorStoreConfig

logger = structlog.get_logger(__name__)


@dataclass
class RetrievedChunk:
    """A chunk retrieved from the vector store."""

    text: str
    metadata: dict[str, Any]
    score: float = 0.0
    source: str = ""


class VectorRetriever:
    """Interface to the vector store for RAG retrieval.

    Supports ChromaDB locally or any compatible vector DB.
    """

    def __init__(self, config: VectorStoreConfig) -> None:
        self._config = config
        self._collection = None
        self._client = None

    async def initialize(self) -> None:
        """Initialize the vector store connection."""
        try:
            import chromadb
            has_full_chromadb = True
        except ImportError:
            has_full_chromadb = False

        try:
            if self._config.host:
                # Use HTTP client (works with chromadb or chromadb-client)
                if has_full_chromadb:
                    self._client = chromadb.HttpClient(
                        host=self._config.host,
                        port=self._config.port or 8000,
                    )
                else:
                    import chromadb_client
                    self._client = chromadb_client.Client(
                        host=self._config.host,
                        port=self._config.port or 8000,
                    )
            elif has_full_chromadb:
                # Use persistent local storage (requires full chromadb)
                self._client = chromadb.PersistentClient(path="./.chromadb")
            else:
                logger.warning("chromadb_not_available", msg="Need chromadb or host config for RAG")
                return

            self._collection = self._client.get_or_create_collection(
                name=self._config.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "vector_store_initialized",
                collection=self._config.collection_name,
                count=self._collection.count(),
            )
        except Exception as exc:
            logger.warning("vector_store_init_failed", error=str(exc))
            self._client = None
            self._collection = None

    async def retrieve(
        self,
        query: str,
        *,
        filter_metadata: dict[str, str] | None = None,
        k: int = 5,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks from the vector store.

        Args:
            query: Natural language query to search for.
            filter_metadata: Optional metadata filter (e.g., {"type": "rule"}).
            k: Number of results to return.

        Returns:
            List of retrieved chunks sorted by relevance.
        """
        if self._collection is None:
            logger.warning("vector_store_not_initialized")
            return []

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": k,
        }
        if filter_metadata:
            kwargs["where"] = filter_metadata

        try:
            results = self._collection.query(**kwargs)
        except Exception as exc:
            logger.error("vector_store_query_failed", error=str(exc))
            return []

        chunks: list[RetrievedChunk] = []
        if results and results["documents"]:
            documents = results["documents"][0]
            metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(documents)
            distances = results["distances"][0] if results["distances"] else [0.0] * len(documents)

            for doc, meta, dist in zip(documents, metadatas, distances):
                chunks.append(
                    RetrievedChunk(
                        text=doc,
                        metadata=meta or {},
                        score=1.0 - dist,  # Convert distance to similarity
                        source=meta.get("source", "") if meta else "",
                    )
                )

        logger.debug("rag_retrieved", query=query[:80], results=len(chunks))
        return chunks

    async def retrieve_rules(self, file_type: str) -> list[RetrievedChunk]:
        """Step 4: Retrieve applicable rules for a file type."""
        return await self.retrieve(
            f"coding rules and conventions for {file_type} files in SW360",
            filter_metadata={"type": "rule"},
            k=8,
        )

    async def retrieve_reference(self, entity: str, file_type: str) -> list[RetrievedChunk]:
        """Step 5: Retrieve reference implementation for an entity."""
        return await self.retrieve(
            f"correct {entity} {file_type} implementation pattern",
            filter_metadata={"type": f"{file_type}_method"},
            k=2,
        )

    async def retrieve_cross_file_context(
        self, entity: str, file_type: str
    ) -> list[RetrievedChunk]:
        """Step 6: Retrieve cross-file context for consistency checks."""
        queries_and_filters = [
            (f"{entity} test method HTTP exercise", {"type": "test_method"}),
            (f"{entity} Jackson mixin customization", {"type": "jackson_mixin"}),
            (f"{entity} handler implementation", {"type": "handler_method"}),
        ]

        all_chunks: list[RetrievedChunk] = []
        for query, filter_meta in queries_and_filters:
            chunks = await self.retrieve(query, filter_metadata=filter_meta, k=2)
            all_chunks.extend(chunks)

        return all_chunks

    async def index_document(
        self, doc_id: str, text: str, metadata: dict[str, Any]
    ) -> None:
        """Add a document to the vector store."""
        if self._collection is None:
            await self.initialize()

        if self._collection:
            self._collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
            )

    async def close(self) -> None:
        """Clean up vector store connection."""
        self._client = None
        self._collection = None

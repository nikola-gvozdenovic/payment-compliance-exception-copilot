"""Query interface over the ingested corpus."""

from pathlib import Path
from typing import Any

import chromadb
from pydantic import BaseModel

from rag.embeddings import get_embedding_function
from rag.ingestion import CHROMA_STORE_PATH, COLLECTION_NAME


class RetrievedChunk(BaseModel):
    """One ranked chunk returned from a query, with citation metadata."""

    chunk_id: str
    doc_id: str
    text: str
    distance: float
    metadata: dict[str, Any]


def retrieve(
    query: str, k: int = 5, persist_path: Path | str = CHROMA_STORE_PATH
) -> list[RetrievedChunk]:
    """Return the k most relevant chunks for a query, ranked by distance (ascending).

    Querying a store that was never ingested into returns an empty list, not an
    error -- get_or_create_collection means there's always a (possibly empty)
    collection to query against.
    """
    client = chromadb.PersistentClient(path=str(persist_path))
    collection = client.get_or_create_collection(
        COLLECTION_NAME, embedding_function=get_embedding_function()
    )
    results = collection.query(query_texts=[query], n_results=k)

    return [
        RetrievedChunk(
            chunk_id=results["ids"][0][i],
            doc_id=results["metadatas"][0][i]["doc_id"],
            text=results["documents"][0][i],
            distance=results["distances"][0][i],
            metadata=results["metadatas"][0][i],
        )
        for i in range(len(results["ids"][0]))
    ]

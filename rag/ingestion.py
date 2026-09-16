"""Chunks and embeds the full TICKET-2 corpus into a local Chroma collection."""

from pathlib import Path

import chromadb

from rag.chunking import chunk_document, parse_document
from rag.embeddings import get_embedding_function

CHROMA_STORE_PATH = Path(__file__).parent / "chroma_store"
COLLECTION_NAME = "compliance_corpus"
CORPUS_DIRS = [
    Path("data/policy_docs"),
    Path("data/sanctions_mock"),
    Path("data/jurisdiction_rules"),
    Path("data/iso20022_reference"),
]


def ingest(persist_path: Path | str = CHROMA_STORE_PATH) -> int:
    """Chunk and embed the full corpus into a local Chroma collection. Idempotent."""
    client = chromadb.PersistentClient(path=str(persist_path))
    collection = client.get_or_create_collection(
        COLLECTION_NAME, embedding_function=get_embedding_function()
    )

    all_chunks = []
    for corpus_dir in CORPUS_DIRS:
        for path in sorted(corpus_dir.glob("*.md")):
            frontmatter, title, body = parse_document(path)
            all_chunks.extend(chunk_document(frontmatter["doc_id"], title, body, frontmatter))

    collection.upsert(
        ids=[c.chunk_id for c in all_chunks],
        documents=[c.text for c in all_chunks],
        metadatas=[c.metadata for c in all_chunks],
    )
    return len(all_chunks)

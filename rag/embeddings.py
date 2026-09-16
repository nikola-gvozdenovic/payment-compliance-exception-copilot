"""Explicit wiring for the embedding function every ingestion/retrieval call uses.

Chroma's bundled default (all-MiniLM-L6-v2, run locally via ONNX -- no external
service, no Ollama) is used deliberately over an Ollama-backed embedding model, so
ingestion and retrieval (and every test that exercises them) never depend on an
Ollama server actually running. See
.claude/plans/ticket-4-rag-ingestion-embedding-retrieval.md NOTES for the full
rationale.
"""

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


def get_embedding_function() -> DefaultEmbeddingFunction:
    return DefaultEmbeddingFunction()

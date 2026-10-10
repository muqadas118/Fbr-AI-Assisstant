import json

import faiss
from sentence_transformers import SentenceTransformer

# Canonical paths / model defaults (single source of truth) — see
# app/hybrid_retriever.py: DEFAULT_INDEX_PATH, DEFAULT_METADATA_PATH,
# EMBEDDING_MODEL_NAME, EMBEDDING_MAX_SEQ_LENGTH, MODEL_REVISION and
# resolve_vectorstore_paths().
from app.hybrid_retriever import (
    EMBEDDING_MAX_SEQ_LENGTH,
    EMBEDDING_MODEL_NAME,
    MODEL_REVISION,
    resolve_vectorstore_paths,
)


class FBRRetriever:

    def __init__(self, index_path=None, metadata_path=None):
        index_path, metadata_path = resolve_vectorstore_paths(
            index_path,
            metadata_path,
        )

        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {index_path}")

        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found: {metadata_path}")

        self.index = faiss.read_index(str(index_path))

        with metadata_path.open("r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        # Same loading flags as the canonical hybrid retriever so both
        # retrievers embed with the identical pinned model revision.
        self.model = SentenceTransformer(
            EMBEDDING_MODEL_NAME,
            revision=MODEL_REVISION,
            local_files_only=True,
        )
        self.model.max_seq_length = EMBEDDING_MAX_SEQ_LENGTH

    def search(self, query, top_k=5):

        embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        embedding = embedding.astype("float32")

        scores, indices = self.index.search(
            embedding,
            top_k,
        )

        results = []

        for score, index in zip(scores[0], indices[0]):

            if index < 0 or index >= len(self.metadata):
                continue

            item = self.metadata[index]

            results.append({
                "score": float(score),
                "source": item.get("source"),
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "text": item.get("text", ""),
            })

        return results

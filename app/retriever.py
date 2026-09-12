from pathlib import Path
import json

import faiss
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parents[1]

VECTOR_DIR = ROOT / "data" / "profile" / "vectorstore"

INDEX_FILE = VECTOR_DIR / "fbr_faiss.index"
METADATA_FILE = VECTOR_DIR / "metadata.json"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class FBRRetriever:

    def __init__(self):
        if not INDEX_FILE.exists():
            raise FileNotFoundError(f"FAISS index not found: {INDEX_FILE}")

        if not METADATA_FILE.exists():
            raise FileNotFoundError(f"Metadata not found: {METADATA_FILE}")

        self.index = faiss.read_index(str(INDEX_FILE))

        with METADATA_FILE.open("r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        self.model = SentenceTransformer(MODEL_NAME)

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
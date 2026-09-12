import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer

ROOT = Path(__file__).resolve().parents[1]

CHUNKS_FILE = (
    ROOT
    / "data"
    / "profile"
    / "source_docs"
    / "chunks"
    / "chunks.json"
)

VECTOR_DIR = ROOT / "data" / "profile" / "vectorstore"

TFIDF_FILE = VECTOR_DIR / "tfidf_vectorizer.joblib"
MATRIX_FILE = VECTOR_DIR / "tfidf_matrix.joblib"


def main():
    print("=" * 60)
    print("FBR KEYWORD INDEX BUILD")
    print("=" * 60)

    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(CHUNKS_FILE)

    VECTOR_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading chunks...")

    with CHUNKS_FILE.open("r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"Chunks loaded : {len(chunks):,}")

    texts = []

    for chunk in chunks:
        text = chunk.get("text", "")

        if not isinstance(text, str):
            text = str(text)

        texts.append(text)

    print()
    print("Building TF-IDF keyword index...")
    print("This may take a few minutes.")

    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        min_df=1,
        max_features=300_000,
        sublinear_tf=True,
        norm="l2",
    )

    matrix = vectorizer.fit_transform(texts)

    print()
    print(f"Matrix shape : {matrix.shape}")
    print(f"Vocabulary   : {len(vectorizer.vocabulary_):,}")

    print()
    print("Saving keyword index...")

    joblib.dump(vectorizer, TFIDF_FILE, compress=3)
    joblib.dump(matrix, MATRIX_FILE, compress=3)

    print()
    print("=" * 60)
    print("KEYWORD INDEX BUILD COMPLETE")
    print("=" * 60)
    print(f"Vectorizer : {TFIDF_FILE}")
    print(f"Matrix     : {MATRIX_FILE}")
    print(f"Documents  : {matrix.shape[0]:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
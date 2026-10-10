import json
import os
import re
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer


MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

# ============================================================
# CANONICAL PATHS / MODEL DEFAULTS (single source of truth)
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

VECTORSTORE_DIRNAME = "vectorstore"
INDEX_FILENAME = "fbr_faiss.index"
METADATA_FILENAME = "metadata.json"
CHUNKS_RELATIVE_PARTS = (
    "data",
    "profile",
    "source_docs",
    "chunks",
    "chunks.json",
)

# Environment overrides. These are the only names other modules
# (retriever, tools) need to know to point at a different index.
INDEX_PATH_ENV = "FBR_VECTORSTORE_INDEX"
METADATA_PATH_ENV = "FBR_VECTORSTORE_METADATA"
CHUNKS_PATH_ENV = "FBR_CHUNKS_PATH"
EMBEDDING_MODEL_ENV = "FBR_EMBEDDING_MODEL"

DEFAULT_INDEX_PATH = (
    PROJECT_ROOT
    / "data"
    / "profile"
    / VECTORSTORE_DIRNAME
    / INDEX_FILENAME
)

DEFAULT_METADATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "profile"
    / VECTORSTORE_DIRNAME
    / METADATA_FILENAME
)

DEFAULT_CHUNKS_PATH = PROJECT_ROOT.joinpath(*CHUNKS_RELATIVE_PARTS)

EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_MAX_SEQ_LENGTH = 256


def resolve_vectorstore_paths(index_path=None, metadata_path=None):
    """
    Resolve the canonical FAISS index / metadata paths.

    Precedence: explicit argument > environment override
    (FBR_VECTORSTORE_INDEX / FBR_VECTORSTORE_METADATA) > project
    default. Shared by every retriever and metadata tool so the
    vectorstore location is never hardcoded in more than one place.
    """

    index = index_path if index_path is not None else os.environ.get(
        INDEX_PATH_ENV, ""
    )
    index = Path(index) if index else DEFAULT_INDEX_PATH

    metadata = (
        metadata_path
        if metadata_path is not None
        else os.environ.get(METADATA_PATH_ENV, "")
    )
    metadata = Path(metadata) if metadata else DEFAULT_METADATA_PATH

    return index, metadata


def default_chunks_path():
    """Canonical chunks.json path (FBR_CHUNKS_PATH to override)."""

    override = os.environ.get(CHUNKS_PATH_ENV, "")
    return Path(override) if override else DEFAULT_CHUNKS_PATH


class FBRHybridRetriever:

    # ============================================================
    # INITIALIZATION
    # ============================================================

    def __init__(
        self,
        index_path=None,
        metadata_path=None,
        embedding_model=None,
    ):
        index_path, metadata_path = resolve_vectorstore_paths(
            index_path,
            metadata_path,
        )

        if embedding_model is None:
            embedding_model = os.environ.get(
                EMBEDDING_MODEL_ENV,
                EMBEDDING_MODEL_NAME,
            )

        # ========================================================
        # LOAD FAISS
        # ========================================================

        print("Loading FAISS index...")
        print(f"FAISS path: {index_path}")

        if not index_path.exists():
            raise FileNotFoundError(
                f"FAISS index not found:\n{index_path}"
            )

        self.index = faiss.read_index(str(index_path))

        # ========================================================
        # LOAD METADATA
        # ========================================================

        print("Loading metadata...")

        if not metadata_path.exists():
            raise FileNotFoundError(
                f"Metadata file not found:\n{metadata_path}"
            )

        with open(metadata_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)

        if not isinstance(self.metadata, list):
            raise RuntimeError(
                "metadata.json must contain a list of records."
            )

        if len(self.metadata) != self.index.ntotal:
            raise RuntimeError(
                "FAISS index size and metadata size do not match.\n"
                f"FAISS vectors : {self.index.ntotal}\n"
                f"Metadata rows : {len(self.metadata)}"
            )

        if type(self.index).__name__ != "IndexFlatIP":
            raise RuntimeError(f"Unsupported FAISS index type: {type(self.index).__name__}")
        if self.index.d != 384 or self.index.metric_type != faiss.METRIC_INNER_PRODUCT:
            raise RuntimeError("FAISS index does not match the normalized 384-dimensional inner-product contract")
        for idx, item in enumerate(self.metadata):
            if item.get("vector_id") != idx or item.get("embedding_index") != idx:
                raise RuntimeError(f"Metadata vector ordering mismatch at row {idx}")

        # ========================================================
        # BUILD VECTOR ID LOOKUP
        # ========================================================

        self.vector_id_to_metadata_index = {}

        for idx, item in enumerate(self.metadata):

            if not isinstance(item, dict):
                continue

            vector_id = item.get("vector_id")

            if vector_id is None:
                continue

            try:
                vector_id = int(vector_id)
            except (TypeError, ValueError):
                continue

            self.vector_id_to_metadata_index[vector_id] = idx

        # ========================================================
        # LOAD EMBEDDING MODEL
        # ========================================================

        print("Loading embedding model...")

        self.model = SentenceTransformer(
            embedding_model,
            revision=MODEL_REVISION,
            local_files_only=True,
        )
        self.model.max_seq_length = EMBEDDING_MAX_SEQ_LENGTH

        # ========================================================
        # BUILD BM25
        # ========================================================

        print("Building BM25 index...")

        self.documents = []
        chunks_path = default_chunks_path()
        with open(chunks_path, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        if len(chunks) != len(self.metadata):
            raise RuntimeError("Canonical chunks and vector metadata counts do not match")
        for index, item in enumerate(self.metadata):
            if chunks[index].get("chunk_id") != item.get("chunk_id"):
                raise RuntimeError(f"Canonical chunk alignment mismatch at row {index}")
            text = str(chunks[index].get("chunk_text") or chunks[index].get("text") or "")
            item["text"] = text
            searchable_metadata = " ".join(
                str(item.get(field, ""))
                for field in (
                    "source",
                    "title",
                    "document_type",
                    "section_reference",
                )
            )
            normalized_source = re.sub(
                r"([a-z])([A-Z])",
                r"\1 \2",
                str(item.get("source", "")),
            )
            self.documents.append(
                f"{text} {searchable_metadata} {normalized_source}"
            )

        tokenized_documents = [
            self._tokenize(text)
            for text in self.documents
        ]

        # ========================================================
        # RUNTIME SECTION REFERENCE EXTRACTION
        # ========================================================

        print("Extracting runtime section references...")

        self._extract_runtime_section_references()

        self.bm25 = BM25Okapi(tokenized_documents)

        print(f"BM25 documents : {len(self.documents)}")

        # ========================================================
        # BUILD EXACT SECTION INDEX
        # ========================================================

        self.section_entries = {}

        for idx, item in enumerate(self.metadata):

            if not isinstance(item, dict):
                continue

            text = str(item.get("text") or item.get("chunk_text") or "")
            source = str(item.get("source", ""))

            if not text:
                continue

            matches = re.finditer(
                r"(?<!\d)(\d{1,3})\.\s+([A-Za-z][^\n]{0,150})",
                text,
            )

            for match in matches:

                section_number = int(match.group(1))
                heading = match.group(2).strip()

                key = (
                    source.lower().strip(),
                    section_number,
                )

                position = match.start()

                score = 0

                if position < 700:
                    score += 3

                if re.search(
                    rf"\b{section_number}\.\s+[A-Za-z]",
                    text,
                ):
                    score += 2

                if "income tax ordinance" in text.lower():
                    score += 1

                existing = self.section_entries.get(key)

                if existing is None or score > existing["score"]:

                    self.section_entries[key] = {
                        "index": idx,
                        "section": section_number,
                        "heading": heading,
                        "source": source,
                        "score": score,
                    }

        print(
            f"Exact section entries : "
            f"{len(self.section_entries)}"
        )

        print("Hybrid retriever ready.")

    # ============================================================
    # RUNTIME SECTION REFERENCE EXTRACTION
    # ============================================================

    _SECTION_HEADING_RE = re.compile(
        r"(?<!\d)(\d{1,3})\.\s+"
        r"([A-Z][A-Za-z][^\n\.\;]{0,200})"
    )

    def _extract_runtime_section_references(self):
        """
        Populate each metadata record's `section_reference` field
        from the chunk text at runtime.

        Phase 5 produced chunks where `section_reference` was never
        populated (it remained None for all 58,822 records). Rather
        than rebuild Phase 5 metadata, we extract the first section
        heading that appears in each chunk's text and inject it as
        the section reference. This is deterministic and never
        touches the FAISS index, the embeddings, or the canonical
        chunks file.
        """

        populated = 0

        for idx, item in enumerate(self.metadata):
            if not isinstance(item, dict):
                continue

            existing = item.get("section_reference")
            if existing:
                continue

            text = str(item.get("text") or "")

            if not text:
                continue

            head = text[:1200]
            match = self._SECTION_HEADING_RE.search(head)
            if not match:
                continue

            section_number = int(match.group(1))
            heading = match.group(2).strip().rstrip(".,;:")

            if 1900 <= section_number <= 2100:
                continue

            heading = re.sub(r"\s+", " ", heading)
            if len(heading) > 120:
                heading = heading[:120].rstrip() + "..."

            section_reference = (
                f"Section {section_number}. {heading}"
            )

            item["section_reference"] = section_reference
            item["section_number"] = section_number
            populated += 1

        print(f"Runtime section references populated: {populated}")

    # ============================================================
    # TOKENIZER
    # ============================================================

    @staticmethod
    def _tokenize(text):

        text = str(text).lower()

        return re.findall(
            r"[a-zA-Z0-9]+",
            text,
        )

    # ============================================================
    # DETECT SECTION QUERY
    # ============================================================

    def _extract_section_query(self, query):

        query_lower = query.lower().strip()

        patterns = [
            r"\bsection\s+(\d{1,3})\b",
            r"\bsec\.?\s*(\d{1,3})\b",
            r"\bs\.?\s*(\d{1,3})\b",
        ]

        section_number = None

        for pattern in patterns:

            match = re.search(
                pattern,
                query_lower,
            )

            if match:

                section_number = int(
                    match.group(1)
                )

                break

        if section_number is None:
            return None

        # Law-intent terms deliberately EXCLUDE "fbr": FBR is the
        # umbrella regulator, not a specific law. Kept in sync with
        # rag_engine._detect_ambiguous_section_query()'s law_terms so
        # both agree that "FBR section 177 rate" is AMBIGUOUS rather
        # than an Income Tax Ordinance section query.
        ordinance_terms = [
            "income tax ordinance",
            "income tax",
            "ordinance 2001",
            "ordinance, 2001",
        ]

        is_ordinance_query = any(
            term in query_lower
            for term in ordinance_terms
        )

        if not is_ordinance_query:
            return None

        return section_number

    def _extract_section_number_only(self, query):
        """
        Lightweight section-number extractor used to detect
        ambiguous section queries (e.g. "What is Section 177?")
        that don't mention a specific law.
        """

        if not query:
            return None

        query_lower = query.lower().strip()

        patterns = [
            r"\bsection\s+(\d{1,3})\b",
            r"\bsec\.?\s*(\d{1,3})\b",
            r"\bs\.?\s*(\d{1,3})\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, query_lower)
            if match:
                return int(match.group(1))

        return None

    def _detect_law_intent(self, query):
        """
        Detect which law the user is asking about.
        Returns a set of law tags. Empty set means ambiguous.
        """

        if not query:
            return set()

        query_lower = query.lower()
        tags = set()

        if any(
            term in query_lower
            for term in (
                "income tax",
                "incometax",
                "ordinance 2001",
                "ordinance, 2001",
            )
        ):
            tags.add("income_tax")

        if any(
            term in query_lower
            for term in ("sales tax", "salestax")
        ):
            tags.add("sales_tax")

        if any(
            term in query_lower
            for term in (
                "federal excise",
                "excise duty",
                "fed_act",
            )
        ):
            tags.add("federal_excise")

        if "finance act" in query_lower:
            tags.add("finance_act")

        if any(
            term in query_lower
            for term in (
                "property valuation",
                "immovable property",
                "property valuation",
            )
        ):
            tags.add("property_valuation")

        return tags

    # ============================================================
    # EXACT SECTION SEARCH
    # ============================================================

    def _exact_section_search(
        self,
        query,
        top_k=5,
    ):

        section_number = self._extract_section_query(
            query
        )

        if section_number is None:
            return []

        candidates = []

        for key, entry in self.section_entries.items():

            source, number = key

            if number != section_number:
                continue

            source_bonus = 0

            if "incometaxordinance2001" in source:
                source_bonus = 100

            elif "income tax ordinance" in source:
                source_bonus = 90

            score = (
                1000
                + source_bonus
                + entry["score"]
            )

            candidates.append(
                {
                    "index": entry["index"],
                    "score": float(score),
                    "semantic_score": 1.0,
                    "bm25_score": 1.0,
                    "exact_match": True,
                }
            )

        candidates.sort(
            key=lambda x: x["score"],
            reverse=True,
        )

        seen = set()
        results = []

        for item in candidates:

            idx = item["index"]

            if idx in seen:
                continue

            seen.add(idx)

            results.append(item)

            if len(results) >= top_k:
                break

        return results

    def _multi_law_section_candidates(
        self,
        section_number,
        laws=None,
        per_law_top_k=1,
    ):
        """
        Find the best exact-section entry for each of the specified
        laws, plus any law not in the list that has an exact match.
        Used to handle ambiguous queries like "What is Section 177?"
        where the user did not name a law.
        """

        if section_number is None:
            return []

        laws = laws or set()
        per_law: dict[str, dict] = {}

        for (source, number), entry in self.section_entries.items():

            if number != section_number:
                continue

            source_l = source.lower()

            law_tag = None
            if "incometaxordinance2001" in source_l or "income tax ordinance" in source_l:
                law_tag = "income_tax"
            elif "salestaxact1990" in source_l or "sales tax act" in source_l:
                law_tag = "sales_tax"
            elif "federalexcise" in source_l or "federal excise" in source_l:
                law_tag = "federal_excise"
            elif "financeact" in source_l or "finance act" in source_l:
                law_tag = "finance_act"
            else:
                law_tag = "other"

            if laws and law_tag not in laws and law_tag != "other":
                continue

            current = per_law.get(law_tag)
            if current is None or entry["score"] > current["entry"]["score"]:
                per_law[law_tag] = {
                    "entry": entry,
                    "source": source,
                    "law_tag": law_tag,
                }

        results = []
        for law_tag, item in per_law.items():
            entry = item["entry"]
            results.append(
                {
                    "index": entry["index"],
                    "score": float(900 + entry["score"]),
                    "semantic_score": 0.85,
                    "bm25_score": 0.85,
                    "exact_match": True,
                    "multi_law_candidate": True,
                    "law_tag": law_tag,
                }
            )

        results.sort(
            key=lambda x: x["score"],
            reverse=True,
        )

        return results

    # ============================================================
    # SECTION CONTINUATION
    # ============================================================

    def _get_section_continuation(
        self,
        query,
        max_chunks=8,
        exact_results=None,
    ):
        """
        Retrieve the complete section continuation.

        For an exact section query:
        1. Find the best exact section chunk.
        2. Keep the same document_id.
        3. Follow sequential vector_ids.
        4. Stop when the next section heading is detected.

        `exact_results` may be supplied by search(), which has already
        run the (O(len(section_entries))) exact-section scan for this
        query — passing it avoids scanning the whole section index a
        second time.
        """

        section_number = self._extract_section_query(
            query
        )

        if section_number is None:
            return []

        if exact_results is None:
            exact_results = self._exact_section_search(
                query,
                top_k=1,
            )

        if not exact_results:
            return []

        start_index = exact_results[0]["index"]

        start_item = self.metadata[start_index]

        document_id = start_item.get(
            "document_id"
        )

        source = str(
            start_item.get(
                "source",
                "",
            )
        )

        vector_id = start_item.get(
            "vector_id"
        )

        if document_id is None:
            return []

        try:
            vector_id = int(vector_id)
        except (TypeError, ValueError):
            return []

        results = []

        # ========================================================
        # FIND NEXT SECTION BOUNDARY
        # ========================================================

        for offset in range(max_chunks):

            current_vector_id = (
                vector_id + offset
            )

            metadata_index = (
                self.vector_id_to_metadata_index.get(
                    current_vector_id
                )
            )

            if metadata_index is None:
                break

            item = self.metadata[
                metadata_index
            ]

            if not isinstance(item, dict):
                break

            # ----------------------------------------------------
            # SECURITY / DOCUMENT ISOLATION
            # ----------------------------------------------------

            if item.get("document_id") != document_id:
                break

            if str(
                item.get("source", "")
            ) != source:
                break

            text = str(
                item.get(
                    "text",
                    "",
                )
            )

            if not text:
                continue

            # ----------------------------------------------------
            # DO NOT STOP ON THE FIRST CHUNK
            # ----------------------------------------------------

            if offset > 0:

                if self._contains_next_section_heading(
                    text,
                    section_number,
                ):
                    break

            results.append(
                {
                    "index": metadata_index,
                    "score": 1.0,
                    "semantic_score": 1.0,
                    "bm25_score": 1.0,
                    "exact_match": True,
                    "section_continuation": True,
                }
            )

        return results

    # ============================================================
    # DETECT NEXT SECTION HEADING
    # ============================================================

    @staticmethod
    def _contains_next_section_heading(
        text,
        current_section,
    ):
        """
        Detect a section heading after the requested section.

        We only consider headings whose number is greater than
        the requested section. This avoids treating references to
        the current section as boundaries.
        """

        pattern = re.compile(
            r"(?<!\d)(\d{1,3})\.\s+"
            r"[A-Za-z][^\n]{0,150}"
        )

        matches = pattern.finditer(text)

        for match in matches:

            number = int(
                match.group(1)
            )

            if number <= current_section:
                continue

            # Ignore obvious year-like values.
            if 1900 <= number <= 2100:
                continue

            # A likely section heading should not be extremely
            # deep inside a sentence.
            prefix = text[
                max(0, match.start() - 80):
                match.start()
            ]

            prefix_lower = prefix.lower()

            boundary_words = [
                "chapter",
                "procedure",
                "section",
                "_____",
                "________________________________",
            ]

            if (
                match.start() < 900
                or any(
                    word in prefix_lower
                    for word in boundary_words
                )
            ):
                return True

        return False

    # ============================================================
    # SEMANTIC SEARCH
    # ============================================================

    def _semantic_search(
        self,
        query,
        top_k=30,
    ):

        query_embedding = self.model.encode(
            [query],
            normalize_embeddings=True,
        )

        query_embedding = np.asarray(
            query_embedding,
            dtype=np.float32,
        )

        scores, indices = self.index.search(
            query_embedding,
            top_k,
        )

        results = {}

        for score, idx in zip(
            scores[0],
            indices[0],
        ):

            idx = int(idx)

            if idx < 0:
                continue

            results[idx] = float(score)

        return results

    # ============================================================
    # BM25 SEARCH
    # ============================================================

    def _bm25_search(
        self,
        query,
        top_k=30,
    ):

        tokens = self._tokenize(query)

        if not tokens:
            return {}

        scores = self.bm25.get_scores(
            tokens
        )

        top_indices = np.argsort(
            scores
        )[::-1][:top_k]

        results = {}

        for idx in top_indices:

            idx = int(idx)

            score = float(
                scores[idx]
            )

            results[idx] = score

        return results

    # ============================================================
    # HYBRID SEARCH
    # ============================================================

    def search(
        self,
        query,
        top_k=5,
    ):

        query = str(query).strip()

        if not query:
            return []

        # ========================================================
        # EXACT SECTION (specific law)
        # ========================================================

        exact_results = self._exact_section_search(
            query,
            top_k=top_k,
        )

        # ========================================================
        # AMBIGUOUS SECTION DETECTION
        # (section number present but no law in query)
        # ========================================================

        law_tags = self._detect_law_intent(query)
        section_number_only = self._extract_section_number_only(query)
        has_specific_section = (
            self._extract_section_query(query) is not None
        )

        if (
            section_number_only is not None
            and not has_specific_section
            and not law_tags
        ):
            multi_law = self._multi_law_section_candidates(
                section_number_only,
                laws=set(),
            )
            if multi_law:
                return multi_law[:top_k]

        # ========================================================
        # SECTION CONTINUATION
        # ========================================================

        continuation_results = (
            self._get_section_continuation(
                query,
                max_chunks=8,
                exact_results=exact_results,
            )
        )

        # ========================================================
        # FOR EXACT SECTION QUESTIONS
        # USE SECTION CONTINUATION AS PRIMARY RESULT
        # ========================================================

        if continuation_results:

            # Keep the primary exact-section hit (it seeds the
            # continuation) instead of dropping it, then append the
            # remaining continuation chunks without duplicates.
            merged = []
            used = set()

            for item in list(exact_results) + list(continuation_results):

                idx = item.get("index")

                if idx in used:
                    continue

                used.add(idx)
                merged.append(item)

            return merged[:top_k]

        # ========================================================
        # NORMAL HYBRID SEARCH
        # ========================================================

        semantic_results = self._semantic_search(
            query,
            top_k=30,
        )

        bm25_results = self._bm25_search(
            query,
            top_k=30,
        )

        # ========================================================
        # NORMALIZE BM25
        # ========================================================

        bm25_max = max(
            bm25_results.values(),
            default=0.0,
        )

        normalized_bm25 = {}

        if bm25_max > 0:

            for idx, score in bm25_results.items():

                normalized_bm25[idx] = (
                    score / bm25_max
                )

        else:

            normalized_bm25 = {
                idx: 0.0
                for idx in bm25_results
            }

        # ========================================================
        # COMBINE
        # ========================================================

        combined = {}

        all_indices = (
            set(semantic_results.keys())
            |
            set(normalized_bm25.keys())
        )

        query_lower = query.lower()
        query_years = set(re.findall(r"\b(?:19|20)\d{2}\b", query_lower))

        for idx in all_indices:

            semantic_score = (
                semantic_results.get(
                    idx,
                    0.0,
                )
            )

            bm25_score_raw = (
                normalized_bm25.get(
                    idx,
                    0.0,
                )
            )

            bm25_score_for_combination = bm25_score_raw

            final_score = (
                0.60 * semantic_score
                +
                0.40 * bm25_score_for_combination
            )

            source_lower = str(
                self.metadata[idx].get("source", "")
            ).lower()
            if "finance act" in query_lower and "financeact" in source_lower:
                if not query_years or any(
                    year in source_lower for year in query_years
                ):
                    final_score += 0.50

            # Corpus-growth follow-up to the documented Phase 8 scoring
            # limitation: the daily updater added 55 official statute
            # documents (+27k chunks), and generic immovable-property
            # valuation queries now match valuation PROVISIONS inside
            # Finance Acts / the Income Tax Ordinance more strongly than
            # the per-city valuation TABLES, which survive only in the
            # BM25 candidate pool. When the query is explicitly about
            # property valuation, apply the same deterministic
            # source-identity boost to the canonical valuation-table
            # documents. No value, rate, year, or section is invented.
            if (
                "valuation" in query_lower
                and "property" in query_lower
                and "propertyvaluation" in source_lower
            ):
                final_score += 0.50

            combined[idx] = {
                "index": idx,
                "score": float(
                    final_score
                ),
                "semantic_score": float(
                    semantic_score
                ),
                "bm25_score": float(
                    bm25_score_for_combination
                ),
                "exact_match": False,
            }

        # ========================================================
        # SORT
        # ========================================================

        normal_results = sorted(
            combined.values(),
            key=lambda x: x["score"],
            reverse=True,
        )

        # ========================================================
        # EXACT RESULTS FIRST
        # ========================================================

        final_results = []
        used_indices = set()

        for item in exact_results:

            idx = item["index"]

            if idx in used_indices:
                continue

            used_indices.add(idx)

            final_results.append(item)

            if len(final_results) >= top_k:
                break

        # ========================================================
        # NORMAL RESULTS
        # ========================================================

        if len(final_results) < top_k:

            for item in normal_results:

                idx = item["index"]

                if idx in used_indices:
                    continue

                used_indices.add(idx)

                final_results.append(item)

                if len(final_results) >= top_k:
                    break

        return final_results[:top_k]

    # ============================================================
    # GET RESULT TEXT
    # ============================================================

    def get_result_text(
        self,
        result,
    ):

        idx = result["index"]

        if idx < 0 or idx >= len(self.metadata):
            return ""

        return str(
            self.metadata[idx].get(
                "text",
                "",
            )
        )

    # ============================================================
    # GET RESULT SOURCE
    # ============================================================

    def get_result_source(
        self,
        result,
    ):

        idx = result["index"]

        if idx < 0 or idx >= len(self.metadata):
            return ""

        return str(
            self.metadata[idx].get(
                "source",
                "",
            )
        )

    # ============================================================
    # GET RESULT CHUNK ID
    # ============================================================

    def get_result_chunk(
        self,
        result,
    ):

        idx = result["index"]

        if idx < 0 or idx >= len(self.metadata):
            return ""

        return str(
            self.metadata[idx].get(
                "chunk_id",
                self.metadata[idx].get(
                    "id",
                    "",
                ),
            )
        )

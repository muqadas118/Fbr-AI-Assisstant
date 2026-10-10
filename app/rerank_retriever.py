import re

from app.hybrid_retriever import FBRHybridRetriever
from app.reranker import FBRReranker


class FBRRerankRetriever:

    def __init__(self):
        self.hybrid = FBRHybridRetriever()
        self.reranker = FBRReranker()

    @staticmethod
    def _extract_sections(query):
        """
        Extract legal section references from the query.

        Examples:
        Section 11
        section 236C
        u/s 236C
        sec. 37(1A)
        """

        pattern = (
            r"\b(?:section|u/s|sec\.?)\s*"
            r"([0-9]+[a-zA-Z]?(?:\([0-9A-Za-z]+\))*)"
        )

        return re.findall(pattern, query.lower())

    @staticmethod
    def _section_priority(query, result):
        """
        Give a small priority boost to documents that contain
        the exact legal section requested by the user.
        """

        sections = FBRRerankRetriever._extract_sections(query)

        if not sections:
            return 0.0

        text = str(result.get("text", "")).lower()

        best_score = 0.0

        for section in sections:

            # Exact "section 11"
            if re.search(
                rf"\bsection\s+{re.escape(section)}\b",
                text
            ):
                best_score = max(best_score, 1.0)

            # u/s 11
            elif re.search(
                rf"\bu/s\s*{re.escape(section)}\b",
                text
            ) or re.search(
                rf"\bsec\.?\s*{re.escape(section)}\b",
                text
            ):
                best_score = max(best_score, 0.9)

        return best_score

    @staticmethod
    def _legal_source_priority(result):
        """
        Prefer the actual Income Tax Ordinance over secondary
        manuals, return forms and unrelated datasets.
        """

        source = str(
            result.get("source", "")
        ).lower()

        if "incometaxordinance" in source:
            return 1.0

        if "wht_rate" in source or "wht_rates" in source:
            return 0.8

        if "manual" in source:
            return 0.6

        return 0.3

    def search(self, query, retrieve_k=50, top_k=5):

        # --------------------------------------------------
        # STEP 1: HYBRID RETRIEVAL
        # --------------------------------------------------

        candidates = self.hybrid.search(
            query,
            top_k=retrieve_k
        )

        if not candidates:
            return []

        # --------------------------------------------------
        # STEP 1b: HYDRATION
        # --------------------------------------------------

        # FBRHybridRetriever.search() returns index/score records
        # only (no text, no source). The cross-encoder and the
        # section/legal-source heuristics below are text-driven, so
        # hydrate every candidate through the canonical accessors
        # first. Without this, term_coverage, section_match and the
        # cross-encoder scores are computed over empty strings.
        for result in candidates:

            if not isinstance(result, dict):
                continue

            if not result.get("text"):
                result["text"] = self.hybrid.get_result_text(result)

            if not result.get("source"):
                result["source"] = self.hybrid.get_result_source(result)

        # --------------------------------------------------
        # STEP 2: SECTION-AWARE PRIORITIZATION
        # --------------------------------------------------

        for result in candidates:

            result["section_priority"] = (
                self._section_priority(
                    query,
                    result
                )
            )

            result["legal_source_priority"] = (
                self._legal_source_priority(
                    result
                )
            )

        # --------------------------------------------------
        # STEP 3: CROSS-ENCODER RERANKING
        # --------------------------------------------------

        reranked = self.reranker.rerank(
            query,
            candidates,
            top_k=retrieve_k
        )

        # --------------------------------------------------
        # STEP 4: FINAL LEGAL PRIORITY
        # --------------------------------------------------

        for result in reranked:

            reranker_score = float(
                result.get(
                    "reranker_final_score",
                    result.get("reranker_score", 0.0)
                )
            )

            section_priority = float(
                result.get(
                    "section_priority",
                    0.0
                )
            )

            legal_source_priority = float(
                result.get(
                    "legal_source_priority",
                    0.0
                )
            )

            # Reranker remains the main signal.
            # Exact legal section gets a strong additional boost.
            # Primary legal source gets a smaller boost.
            final_score = (
                reranker_score
                + (4.0 * section_priority)
                + (1.0 * legal_source_priority)
            )

            result["final_rerank_score"] = final_score

        # --------------------------------------------------
        # STEP 5: SORT
        # --------------------------------------------------

        reranked.sort(
            key=lambda x: x.get(
                "final_rerank_score",
                float("-inf")
            ),
            reverse=True
        )

        return reranked[:top_k]
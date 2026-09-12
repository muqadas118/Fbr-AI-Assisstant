import re
from sentence_transformers import CrossEncoder


MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class FBRReranker:

    def __init__(self):
        print("Loading reranker model...")
        self.model = CrossEncoder(MODEL_NAME)

    # ---------------------------------------------------------
    # TEXT NORMALIZATION
    # ---------------------------------------------------------

    @staticmethod
    def _normalize(text):
        text = str(text).lower()
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # ---------------------------------------------------------
    # SECTION EXTRACTION
    # ---------------------------------------------------------

    @staticmethod
    def _extract_sections(query):
        """
        Detect legal section references such as:

        Section 11
        section 236C
        u/s 236C
        sec 37(1A)
        section 100BA
        """

        pattern = (
            r"\b(?:section|u/s|sec\.?)\s*"
            r"([0-9]+[a-zA-Z]?"
            r"(?:\([0-9A-Za-z]+\))*)"
        )

        return re.findall(
            pattern,
            query.lower()
        )

    # ---------------------------------------------------------
    # SECTION MATCH
    # ---------------------------------------------------------

    @staticmethod
    def _section_match(query, text):

        query_sections = FBRReranker._extract_sections(query)

        if not query_sections:
            return 0.0

        text_normalized = FBRReranker._normalize(text)

        matched = 0

        for section in query_sections:

            patterns = [
                rf"\bsection\s+{re.escape(section)}\b",
                rf"\bu/s\s*{re.escape(section)}\b",
                rf"\bsec\.?\s*{re.escape(section)}\b",
            ]

            # Also allow section headings such as:
            #
            # 11. Heads of income
            # 236C Transfer of Immovable Property

            heading_pattern = (
                rf"(?:^|\s)"
                rf"{re.escape(section)}"
                rf"\s*[\.\:\-]"
            )

            found = (
                any(
                    re.search(
                        pattern,
                        text_normalized
                    )
                    for pattern in patterns
                )
                or re.search(
                    heading_pattern,
                    text_normalized
                )
            )

            if found:
                matched += 1

        return matched / len(query_sections)

    # ---------------------------------------------------------
    # QUERY TERM COVERAGE
    # ---------------------------------------------------------

    @staticmethod
    def _query_terms(query):

        stopwords = {
            "what",
            "is",
            "are",
            "the",
            "of",
            "under",
            "in",
            "on",
            "for",
            "to",
            "a",
            "an",
            "and",
            "or",
            "from",
            "does",
            "do",
            "how",
            "which",
            "when",
            "where",
            "who",
        }

        words = re.findall(
            r"[a-zA-Z0-9]+",
            query.lower()
        )

        return [
            word
            for word in words
            if word not in stopwords
            and len(word) > 1
        ]

    @staticmethod
    def _term_coverage(query, text):

        terms = FBRReranker._query_terms(query)

        if not terms:
            return 0.0

        text_normalized = FBRReranker._normalize(text)

        matched = 0

        for term in terms:
            if term in text_normalized:
                matched += 1

        return matched / len(terms)

    # ---------------------------------------------------------
    # LEGAL SOURCE SCORE
    # ---------------------------------------------------------

    @staticmethod
    def _source_score(result):

        source = FBRReranker._normalize(
            result.get("source", "")
        )

        # Primary legislation
        if "incometaxordinance" in source:
            return 1.0

        # FBR withholding tax material
        if (
            "wht_rate" in source
            or "wht_rates" in source
        ):
            return 0.90

        # Manuals / SOPs
        if (
            "manual" in source
            or "sop" in source
        ):
            return 0.75

        return 0.50

    # ---------------------------------------------------------
    # EXACT SECTION HEADING BOOST
    # ---------------------------------------------------------

    @staticmethod
    def _section_heading_match(query, text):

        sections = FBRReranker._extract_sections(query)

        if not sections:
            return 0.0

        normalized = FBRReranker._normalize(text)

        for section in sections:

            # Examples:
            #
            # 11. Heads of income
            # 236C. Transfer of immovable property
            # 37(1A) Capital gains

            patterns = [
                rf"\b{re.escape(section)}\s*\.\s*[a-z]",
                rf"\b{re.escape(section)}\s*:"
            ]

            if any(
                re.search(pattern, normalized)
                for pattern in patterns
            ):
                return 1.0

        return 0.0

    # ---------------------------------------------------------
    # MAIN RERANK
    # ---------------------------------------------------------

    def rerank(self, query, results, top_k=5):

        if not results:
            return []

        pairs = [
            [
                query,
                result.get("text", "")
            ]
            for result in results
        ]

        model_scores = self.model.predict(pairs)

        scored = []

        for result, model_score in zip(
            results,
            model_scores
        ):

            text = result.get("text", "")

            semantic_score = float(
                result.get("semantic_score", 0.0)
            )

            bm25_score = float(
                result.get("bm25_score", 0.0)
            )

            section_match = self._section_match(
                query,
                text
            )

            heading_match = self._section_heading_match(
                query,
                text
            )

            term_coverage = self._term_coverage(
                query,
                text
            )

            source_score = self._source_score(
                result
            )

            # -------------------------------------------------
            # NORMALIZE BM25
            # -------------------------------------------------

            # BM25 can have a much larger numerical range
            # than semantic/cross-encoder scores.
            #
            # We only use a small contribution here because
            # lexical relevance is already represented by
            # term coverage.

            bm25_signal = min(
                bm25_score / 50.0,
                1.0
            )

            # -------------------------------------------------
            # FINAL SCORE
            # -------------------------------------------------

            final_score = (
                (0.45 * float(model_score))
                + (1.50 * semantic_score)
                + (0.80 * bm25_signal)
                + (2.50 * term_coverage)
                + (4.00 * section_match)
                + (5.00 * heading_match)
                + (0.35 * source_score)
            )

            item = result.copy()

            item["reranker_score"] = float(
                model_score
            )

            item["section_match_score"] = float(
                section_match
            )

            item["section_heading_score"] = float(
                heading_match
            )

            item["term_coverage_score"] = float(
                term_coverage
            )

            item["source_score"] = float(
                source_score
            )

            item["reranker_final_score"] = float(
                final_score
            )

            scored.append(item)

        scored.sort(
            key=lambda x: x["reranker_final_score"],
            reverse=True
        )

        return scored[:top_k]
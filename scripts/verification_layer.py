import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


# ============================================================
# VERIFICATION RESULT
# ============================================================

@dataclass
class VerificationResult:
    passed: bool
    confidence: float
    reasons: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "confidence": round(self.confidence, 3),
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


# ============================================================
# FBR ANSWER VERIFICATION LAYER
# ============================================================

class FBRAnswerVerifier:

    MAX_ANSWER_LENGTH = 20000
    MIN_ANSWER_LENGTH = 20

    # Conservative thresholds.
    MIN_CONTEXT_MATCH = 0.08
    STRONG_CONTEXT_MATCH = 0.18

    def __init__(self):
        print("FBR Verification Layer ready.")

    # --------------------------------------------------------
    # NORMALIZATION
    # --------------------------------------------------------

    @staticmethod
    def normalize(text: str) -> str:
        if not isinstance(text, str):
            return ""

        text = text.lower()
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^\w\s.%/-]", " ", text)

        return text.strip()

    # --------------------------------------------------------
    # TOKENIZATION
    # --------------------------------------------------------

    @staticmethod
    def tokens(text: str) -> set:
        normalized = FBRAnswerVerifier.normalize(text)

        if not normalized:
            return set()

        return {
            token
            for token in normalized.split()
            if len(token) >= 3
        }

    # --------------------------------------------------------
    # EXTRACT SOURCES
    # --------------------------------------------------------

    @staticmethod
    def extract_sources(context: str) -> list[str]:
        if not context:
            return []

        sources = re.findall(
            r"Document:\s*(.+)",
            context,
            flags=re.IGNORECASE
        )

        unique = []

        for source in sources:
            source = source.strip()

            if source and source not in unique:
                unique.append(source)

        return unique

    # --------------------------------------------------------
    # EXTRACT SECTION NUMBERS
    # --------------------------------------------------------

    @staticmethod
    def extract_sections(text: str) -> list[str]:
        if not text:
            return []

        matches = re.findall(
            r"\bsection\s+(\d+[A-Za-z]?)\b",
            text,
            flags=re.IGNORECASE
        )

        return list(dict.fromkeys(matches))

    # --------------------------------------------------------
    # EXTRACT IMPORTANT NUMBERS
    # --------------------------------------------------------

    @staticmethod
    def extract_numeric_values(text: str) -> set:
        if not text:
            return set()

        return set(
            re.findall(
                r"\b\d+(?:\.\d+)?%?\b",
                text
            )
        )

    # --------------------------------------------------------
    # TEXT SIMILARITY
    # --------------------------------------------------------

    @staticmethod
    def similarity(a: str, b: str) -> float:
        a = FBRAnswerVerifier.normalize(a)
        b = FBRAnswerVerifier.normalize(b)

        if not a or not b:
            return 0.0

        return SequenceMatcher(None, a, b).ratio()

    # --------------------------------------------------------
    # TOKEN OVERLAP
    # --------------------------------------------------------

    def context_overlap(self, answer: str, context: str) -> float:
        answer_tokens = self.tokens(answer)
        context_tokens = self.tokens(context)

        if not answer_tokens or not context_tokens:
            return 0.0

        overlap = answer_tokens.intersection(context_tokens)

        return len(overlap) / len(answer_tokens)

    # --------------------------------------------------------
    # SENTENCE SPLIT
    # --------------------------------------------------------

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        if not text:
            return []

        sentences = re.split(
            r"(?<=[.!?])\s+",
            text.strip()
        )

        return [
            sentence.strip()
            for sentence in sentences
            if sentence.strip()
        ]

    # --------------------------------------------------------
    # SENTENCE GROUNDING
    # --------------------------------------------------------

    def sentence_grounding(
        self,
        answer: str,
        context: str
    ) -> dict[str, Any]:

        sentences = self.split_sentences(answer)

        if not sentences:
            return {
                "supported": 0,
                "total": 0,
                "ratio": 0.0,
                "unsupported": []
            }

        context_normalized = self.normalize(context)

        supported = 0
        unsupported = []

        for sentence in sentences:

            sentence_tokens = self.tokens(sentence)

            if not sentence_tokens:
                continue

            context_tokens = self.tokens(context)

            overlap = (
                len(sentence_tokens.intersection(context_tokens))
                / max(len(sentence_tokens), 1)
            )

            direct_similarity = self.similarity(
                sentence,
                context_normalized
            )

            # Conservative grounding rule.
            if (
                overlap >= self.MIN_CONTEXT_MATCH
                or direct_similarity >= 0.25
            ):
                supported += 1
            else:
                unsupported.append(sentence)

        ratio = supported / max(len(sentences), 1)

        return {
            "supported": supported,
            "total": len(sentences),
            "ratio": ratio,
            "unsupported": unsupported,
        }

    # --------------------------------------------------------
    # QUESTION TOPIC CHECK
    # --------------------------------------------------------

    def question_topic_check(
        self,
        question: str,
        answer: str
    ) -> bool:

        question_tokens = self.tokens(question)
        answer_tokens = self.tokens(answer)

        if not question_tokens or not answer_tokens:
            return False

        overlap = question_tokens.intersection(answer_tokens)

        return len(overlap) >= 1

    # --------------------------------------------------------
    # SECTION CONSISTENCY
    # --------------------------------------------------------

    def section_consistency(
        self,
        question: str,
        answer: str,
        context: str
    ) -> dict[str, Any]:

        question_sections = self.extract_sections(question)
        answer_sections = self.extract_sections(answer)
        context_sections = self.extract_sections(context)

        if not question_sections:
            return {
                "checked": False,
                "passed": True,
                "reason": "No explicit section number in question."
            }

        for section in question_sections:

            if section not in context_sections:
                return {
                    "checked": True,
                    "passed": False,
                    "reason": (
                        f"Section {section} requested by the question "
                        f"was not found in retrieved context."
                    )
                }

            if section not in answer_sections:
                return {
                    "checked": True,
                    "passed": False,
                    "reason": (
                        f"Answer does not explicitly identify "
                        f"Section {section}."
                    )
                }

        return {
            "checked": True,
            "passed": True,
            "reason": "Section references are consistent."
        }

    # --------------------------------------------------------
    # NUMERIC CONSISTENCY
    # --------------------------------------------------------

    def numeric_consistency(
        self,
        answer: str,
        context: str
    ) -> dict[str, Any]:

        answer_numbers = self.extract_numeric_values(answer)
        context_numbers = self.extract_numeric_values(context)

        if not answer_numbers:
            return {
                "checked": False,
                "passed": True,
                "unexpected": []
            }

        unexpected = sorted(
            answer_numbers - context_numbers
        )

        # Numbers are high-risk in tax answers.
        # Any new numeric claim requires evidence.
        passed = len(unexpected) == 0

        return {
            "checked": True,
            "passed": passed,
            "unexpected": unexpected,
        }

    # --------------------------------------------------------
    # CONTRADICTION SIGNALS
    # --------------------------------------------------------

    def contradiction_check(
        self,
        answer: str
    ) -> dict[str, Any]:

        normalized = self.normalize(answer)

        contradiction_patterns = [
            r"\bhowever\b",
            r"\bbut\b",
            r"\binstead\b",
            r"\bcontrary\b",
            r"\bnotwithstanding\b",
        ]

        found = []

        for pattern in contradiction_patterns:
            if re.search(pattern, normalized):
                found.append(pattern.replace(r"\b", ""))

        return {
            "checked": True,
            "signals": found,
        }

    # --------------------------------------------------------
    # MAIN VERIFICATION
    # --------------------------------------------------------

    def verify(
        self,
        question: str,
        answer: str,
        context: str
    ) -> VerificationResult:

        reasons = []
        warnings = []

        # ----------------------------------------------------
        # BASIC INPUT VALIDATION
        # ----------------------------------------------------

        if not isinstance(question, str) or not question.strip():
            return VerificationResult(
                passed=False,
                confidence=0.0,
                reasons=["Question is empty."],
                warnings=[]
            )

        if not isinstance(answer, str) or not answer.strip():
            return VerificationResult(
                passed=False,
                confidence=0.0,
                reasons=["Generated answer is empty."],
                warnings=[]
            )

        if len(answer) > self.MAX_ANSWER_LENGTH:
            return VerificationResult(
                passed=False,
                confidence=0.0,
                reasons=["Generated answer exceeds maximum length."],
                warnings=[]
            )

        if len(answer.strip()) < self.MIN_ANSWER_LENGTH:
            return VerificationResult(
                passed=False,
                confidence=0.0,
                reasons=["Generated answer is too short to verify."],
                warnings=[]
            )

        if not isinstance(context, str) or not context.strip():
            return VerificationResult(
                passed=False,
                confidence=0.0,
                reasons=["No retrieval context was supplied."],
                warnings=[]
            )

        # ----------------------------------------------------
        # SOURCE CHECK
        # ----------------------------------------------------

        sources = self.extract_sources(context)

        if not sources:
            return VerificationResult(
                passed=False,
                confidence=0.0,
                reasons=["No source documents were found in context."],
                warnings=[]
            )

        reasons.append(
            f"{len(sources)} source document(s) available."
        )

        # ----------------------------------------------------
        # CONTEXT OVERLAP
        # ----------------------------------------------------

        overlap = self.context_overlap(
            answer,
            context
        )

        if overlap < self.MIN_CONTEXT_MATCH:
            return VerificationResult(
                passed=False,
                confidence=0.15,
                reasons=[
                    (
                        "Answer has insufficient lexical grounding "
                        "in the retrieved context."
                    )
                ],
                warnings=[]
            )

        reasons.append(
            f"Context token overlap: {overlap:.2%}"
        )

        # ----------------------------------------------------
        # SENTENCE GROUNDING
        # ----------------------------------------------------

        grounding = self.sentence_grounding(
            answer,
            context
        )

        grounding_ratio = grounding["ratio"]

        if grounding_ratio < 0.60:
            return VerificationResult(
                passed=False,
                confidence=min(0.45, grounding_ratio),
                reasons=[
                    (
                        "Too many answer sentences could not be grounded "
                        "against the retrieved evidence."
                    )
                ],
                warnings=grounding["unsupported"][:3]
            )

        reasons.append(
            f"Grounded sentences: "
            f"{grounding['supported']}/{grounding['total']}"
        )

        # ----------------------------------------------------
        # QUESTION TOPIC
        # ----------------------------------------------------

        if not self.question_topic_check(
            question,
            answer
        ):
            return VerificationResult(
                passed=False,
                confidence=0.30,
                reasons=[
                    (
                        "Answer does not sufficiently match "
                        "the question topic."
                    )
                ],
                warnings=[]
            )

        reasons.append("Answer matches the question topic.")

        # ----------------------------------------------------
        # SECTION CHECK
        # ----------------------------------------------------

        section_check = self.section_consistency(
            question,
            answer,
            context
        )

        if not section_check["passed"]:

            return VerificationResult(
                passed=False,
                confidence=0.35,
                reasons=[section_check["reason"]],
                warnings=[]
            )

        reasons.append(
            section_check["reason"]
        )

        # ----------------------------------------------------
        # NUMERIC CHECK
        # ----------------------------------------------------

        numeric_check = self.numeric_consistency(
            answer,
            context
        )

        if not numeric_check["passed"]:

            return VerificationResult(
                passed=False,
                confidence=0.35,
                reasons=[
                    (
                        "Answer contains numeric values that are not "
                        "supported by the retrieved context."
                    )
                ],
                warnings=numeric_check["unexpected"]
            )

        if numeric_check["checked"]:
            reasons.append(
                "Numeric claims are supported by context."
            )

        # ----------------------------------------------------
        # CONTRADICTION SIGNALS
        # ----------------------------------------------------

        contradiction = self.contradiction_check(answer)

        if contradiction["signals"]:
            warnings.append(
                "Answer contains possible contrast/contradiction "
                "language and should receive additional review."
            )

        # ----------------------------------------------------
        # FINAL CONFIDENCE
        # ----------------------------------------------------

        confidence = 0.70

        if overlap >= self.STRONG_CONTEXT_MATCH:
            confidence += 0.10

        if grounding_ratio >= 0.80:
            confidence += 0.10

        if section_check["passed"]:
            confidence += 0.05

        if numeric_check["passed"]:
            confidence += 0.05

        confidence = min(confidence, 1.0)

        # High-quality answer requirement.
        passed = confidence >= 0.80

        if passed:
            reasons.append(
                "Answer passed the verification threshold."
            )
        else:
            reasons.append(
                "Answer did not reach the verification threshold."
            )

        return VerificationResult(
            passed=passed,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings
        )


# ============================================================
# SIMPLE TEST
# ============================================================

if __name__ == "__main__":

    verifier = FBRAnswerVerifier()

    question = (
        "What is Section 177 of the Income Tax Ordinance 2001?"
    )

    context = """
    Document: IncomeTaxOrdinance2001_upto2025.pdf

    177. Audit. The Commissioner may call for any record or
    documents including books of accounts for conducting audit
    of the income tax affairs of the person.
    """

    answer = """
    Section 177 of the Income Tax Ordinance 2001 deals with
    audit. The Commissioner may call for records and books of
    accounts for conducting an audit of the person's income
    tax affairs.
    """

    result = verifier.verify(
        question,
        answer,
        context
    )

    print("=" * 60)
    print("FBR VERIFICATION LAYER TEST")
    print("=" * 60)

    print(f"Passed     : {result.passed}")
    print(f"Confidence : {result.confidence:.3f}")

    print("\nReasons:")
    for reason in result.reasons:
        print(f"- {reason}")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"- {warning}")

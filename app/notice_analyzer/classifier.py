"""
Notice Classifier - Production-Grade
=====================================

Classifies FBR notices into 30+ types using keyword/regex signals.

FBR Notice Types:
- Show Cause Notice (SCN) - Section 114(3), 122, 161
- Assessment Order - Section 120, 121
- Recovery Notice - Section 138
- Penalty Notice - Section 182, 184
- Demand Notice - Section 137
- Intimation - Section 143
- Audit Notice - Section 214C
- Enquiry Notice - Section 176
- Refund Notice
- Amendment Notice
- Provisional Assessment
- Final Assessment
- Best Judgment Assessment
- Wealth Statement Notice
- Taxpayer Notice (general)
- Arrears Notice
- Compliance Notice
- Rectification Notice
- Revision Notice
- Appeal Order
- Stay Order
- Attachment Notice
- Prosecution Notice
- Survey Notice
- Sealing Notice
- Seizure Notice
- Auction Notice
- Tax Evasion Notice
- Audit Selection Notice
- Information Request
- Reconciliation Notice
- Adjustment Notice
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re


class NoticeType(str, Enum):
    """All FBR notice types."""
    SHOW_CAUSE_114 = "show_cause_section_114"  # 114(3)
    SHOW_CAUSE_122 = "show_cause_section_122"  # 122(1)
    SHOW_CAUSE_161 = "show_cause_section_161"  # 161
    SHOW_CAUSE_GENERAL = "show_cause_general"

    ASSESSMENT_120 = "assessment_section_120"  # 120
    ASSESSMENT_121 = "assessment_section_121"  # 121
    ASSESSMENT_122 = "assessment_section_122"  # 122(4) - final after SCN
    PROVISIONAL_ASSESSMENT = "provisional_assessment"
    BEST_JUDGMENT = "best_judgment"
    AMENDED_ASSESSMENT = "amended_assessment"

    DEMAND_137 = "demand_section_137"
    RECOVERY_138 = "recovery_section_138"
    ARREARS_NOTICE = "arrears_notice"

    PENALTY_182 = "penalty_section_182"
    PENALTY_184 = "penalty_section_184"
    PENALTY_GENERAL = "penalty_general"

    AUDIT_214C = "audit_section_214C"
    AUDIT_SELECTION = "audit_selection"
    ENQUIRY_176 = "enquiry_section_176"

    INTIMATION_143 = "intimation_section_143"
    RECTIFICATION = "rectification"
    REVISION = "revision"
    AMENDMENT = "amendment"

    REFUND_NOTICE = "refund_notice"
    WEALTH_STATEMENT = "wealth_statement"
    COMPLIANCE_NOTICE = "compliance_notice"

    APPEAL_ORDER = "appeal_order"
    STAY_ORDER = "stay_order"

    PROSECUTION = "prosecution"
    SURVEY = "survey"
    ATTACHMENT = "attachment"
    SEIZURE = "seizure"
    AUCTION = "auction"
    SEALING = "sealing"

    INFORMATION_REQUEST = "information_request"
    RECONCILIATION = "reconciliation"
    ADJUSTMENT = "adjustment"

    UNKNOWN = "unknown"


# Classification signals - keywords/regex patterns
# Format: notice_type -> list of (signal, weight)
CLASSIFICATION_SIGNALS = {
    NoticeType.SHOW_CAUSE_114: [
        ("show cause", 5),
        ("section 114", 10),
        ("114(3)", 10),
        ("explanation", 3),
        ("why proceedings", 3),
    ],
    NoticeType.SHOW_CAUSE_122: [
        ("show cause", 5),
        ("section 122", 10),
        ("122(1)", 10),
        ("concealment", 5),
        ("misrepresentation", 4),
    ],
    NoticeType.ASSESSMENT_120: [
        ("assessment", 5),
        ("section 120", 10),
        ("120(1)", 10),
        ("determined", 3),
    ],
    NoticeType.ASSESSMENT_121: [
        ("assessment", 5),
        ("section 121", 10),
        ("121(1)", 10),
    ],
    NoticeType.ASSESSMENT_122: [
        ("order under section 122", 10),
        ("final assessment", 8),
        ("section 122(4)", 10),
    ],
    NoticeType.DEMAND_137: [
        ("demand", 5),
        ("section 137", 10),
        ("137(1)", 10),
        ("payable", 3),
    ],
    NoticeType.RECOVERY_138: [
        ("recovery", 5),
        ("section 138", 10),
        ("138(1)", 10),
        ("recover", 4),
    ],
    NoticeType.PENALTY_182: [
        ("penalty", 5),
        ("section 182", 10),
        ("182(1)", 10),
        ("punishment", 4),
    ],
    NoticeType.PENALTY_184: [
        ("penalty", 5),
        ("section 184", 10),
        ("184(1)", 10),
    ],
    NoticeType.AUDIT_214C: [
        ("audit", 5),
        ("section 214C", 10),
        ("214C", 10),
        ("audit selection", 8),
    ],
    NoticeType.ENQUIRY_176: [
        ("enquiry", 5),
        ("section 176", 10),
        ("investigation", 4),
    ],
    NoticeType.INTIMATION_143: [
        ("intimation", 5),
        ("section 143", 10),
        ("143(1)", 10),
    ],
    NoticeType.RECTIFICATION: [
        ("rectification", 6),
        ("section 156", 8),
        ("correction", 3),
    ],
    NoticeType.REVISION: [
        ("revision", 6),
        ("section 122A", 8),
        ("122A", 8),
    ],
    NoticeType.WEALTH_STATEMENT: [
        ("wealth statement", 8),
        ("wealth reconciliation", 10),
        ("section 116", 6),
    ],
    NoticeType.REFUND_NOTICE: [
        ("refund", 6),
        ("section 170", 8),
        ("170(1)", 8),
    ],
    NoticeType.PROSECUTION: [
        ("prosecution", 8),
        ("criminal proceedings", 8),
        ("section 191", 8),
    ],
    NoticeType.ATTACHMENT: [
        ("attachment", 6),
        ("section 140", 8),
    ],
    NoticeType.SEIZURE: [
        ("seizure", 6),
        ("section 138", 4),
        ("seize", 5),
    ],
    NoticeType.SURVEY: [
        ("survey", 6),
        ("section 175", 8),
    ],
    NoticeType.AUCTION: [
        ("auction", 6),
        ("section 142", 8),
    ],
    NoticeType.INFORMATION_REQUEST: [
        ("information", 4),
        ("provide", 3),
        ("furnish", 3),
        ("require", 4),
    ],
}


@dataclass
class ClassificationResult:
    """Result of notice classification."""
    notice_type: NoticeType
    confidence: float  # 0-1
    matched_signals: list[str] = field(default_factory=list)
    score_breakdown: dict = field(default_factory=dict)
    secondary_types: list[tuple[NoticeType, float]] = field(default_factory=list)
    is_appealable: bool = False
    is_critical: bool = False


class NoticeClassifier:
    """Production-grade notice classifier using weighted keyword signals."""

    # Notice types that require urgent action
    CRITICAL_TYPES = {
        NoticeType.SHOW_CAUSE_122,
        NoticeType.SHOW_CAUSE_114,
        NoticeType.ASSESSMENT_122,
        NoticeType.DEMAND_137,
        NoticeType.RECOVERY_138,
        NoticeType.PENALTY_182,
        NoticeType.PENALTY_184,
        NoticeType.PROSECUTION,
        NoticeType.ATTACHMENT,
        NoticeType.SEIZURE,
    }

    # Notice types that can be appealed
    APPEALABLE_TYPES = {
        NoticeType.SHOW_CAUSE_114,
        NoticeType.SHOW_CAUSE_122,
        NoticeType.SHOW_CAUSE_161,
        NoticeType.ASSESSMENT_120,
        NoticeType.ASSESSMENT_121,
        NoticeType.ASSESSMENT_122,
        NoticeType.PENALTY_182,
        NoticeType.PENALTY_184,
        NoticeType.RECOVERY_138,
        NoticeType.DEMAND_137,
        NoticeType.AUDIT_214C,
    }

    @staticmethod
    def classify(text: str) -> ClassificationResult:
        """
        Classify notice text into FBR notice type.

        Args:
            text: Notice text (extracted from PDF/Image)

        Returns:
            ClassificationResult with type, confidence, and details
        """
        if not text or len(text.strip()) < 10:
            return ClassificationResult(
                notice_type=NoticeType.UNKNOWN,
                confidence=0.0,
            )

        text_lower = text.lower()
        # Real FBR notices commonly write "u/s 114(4)" / "U/S. 122" —
        # normalize to "section ..." so the section signals match.
        text_lower = re.sub(r"\bu[./\s]*s\.?\s*", "section ", text_lower)

        # Score each notice type
        scores: dict[NoticeType, tuple[float, list[str], dict, list[tuple[str, int]]]] = {}
        for notice_type, signals in CLASSIFICATION_SIGNALS.items():
            total_score = 0
            matched = []
            breakdown = {}
            matched_pairs: list[tuple[str, int]] = []
            for signal, weight in signals:
                count = text_lower.count(signal.lower())
                if count == 0:
                    # Subsection-specific signals like "114(3)" also match any
                    # other subsection of the same section ("114(4)", "114(").
                    if re.fullmatch(r"\d+[A-Z]?\(\d+[A-Z]?\)", signal.lower()):
                        base = signal.lower().split("(", 1)[0]
                        count = text_lower.count(base + "(")
                        if count:
                            weight = max(6, weight - 2)
                if count > 0:
                    total_score += weight * count
                    matched.append(signal)
                    matched_pairs.append((signal, weight))
                    breakdown[signal] = count
            if total_score > 0:
                scores[notice_type] = (total_score, matched, breakdown, matched_pairs)

        if not scores:
            return ClassificationResult(
                notice_type=NoticeType.UNKNOWN,
                confidence=0.0,
            )

        # Sort by score
        sorted_scores = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
        top_type, (top_score, top_matched, top_breakdown, top_pairs) = sorted_scores[0]

        # Confidence: a specific section reference is strong evidence —
        # start high and add a little for every corroborating signal.
        # Generic keyword-only matches keep the conservative score/50 scale.
        if any(w >= 8 for _s, w in top_pairs):
            confidence = min(0.75 + 0.05 * (len(top_pairs) - 1), 0.97)
        else:
            confidence = min(top_score / 50.0, 1.0)

        # Get secondary types
        secondary = [
            (t, s[0] / 50.0)
            for t, s in sorted_scores[1:4]
        ]

        is_critical = top_type in NoticeClassifier.CRITICAL_TYPES
        is_appealable = top_type in NoticeClassifier.APPEALABLE_TYPES

        return ClassificationResult(
            notice_type=top_type,
            confidence=round(confidence, 2),
            matched_signals=top_matched,
            score_breakdown=top_breakdown,
            secondary_types=[(t, round(c, 2)) for t, c in secondary],
            is_appealable=is_appealable,
            is_critical=is_critical,
        )

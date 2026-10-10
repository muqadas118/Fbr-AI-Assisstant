"""
Appeal Guide Generator - Production-Grade
==========================================

Generates detailed appeal guides for FBR notices.

FBR Appeal Hierarchy:
1. Commissioner (Appeals) [CIR-A] - First appellate authority (30 days)
2. Appellate Tribunal Inland Revenue [ATIR] - Second appeal (60 days)
3. High Court - Reference (90 days from ATIR order)
4. Supreme Court - Appeal (leave to appeal, 90 days)

Each stage has specific:
- Forms required
- Documents needed
- Fees
- Time limits
- Common grounds
- Success rate
"""

from dataclasses import dataclass, field
from enum import Enum

from app.notice_analyzer.classifier import NoticeClassifier, NoticeType


class AppealForum(str, Enum):
    """FBR appeal forums."""
    CIR_A = "commissioner_appeals"  # First appeal
    ATIR = "appellate_tribunal"  # Second appeal
    HIGH_COURT = "high_court"  # Reference
    SUPREME_COURT = "supreme_court"  # Final appeal


@dataclass
class AppealGuide:
    """Complete appeal guide."""
    notice_type: str
    forum: str
    time_limit_days: int
    is_appealable: bool
    forms_required: list[str] = field(default_factory=list)
    documents_needed: list[str] = field(default_factory=list)
    fees_required: str = ""
    common_grounds: list[str] = field(default_factory=list)
    success_factors: list[str] = field(default_factory=list)
    typical_success_rate: str = ""
    estimated_cost: str = ""
    notes: list[str] = field(default_factory=list)


class AppealGuideGenerator:
    """Generates appeal guides for notices."""

    @staticmethod
    def generate(notice_type: NoticeType) -> AppealGuide:
        """Generate appeal guide for notice type.

        RULE (single source of truth): appealability comes from
        NoticeClassifier.APPEALABLE_TYPES and nowhere else. The branches below
        only describe HOW to appeal (forum, time limit, forms); they never
        decide WHETHER a notice is appealable, so the guide and the top-level
        classification always agree.
        """
        is_appealable = notice_type in NoticeClassifier.APPEALABLE_TYPES

        # First appeal (CIR-A) - common for most
        if notice_type in {
            NoticeType.SHOW_CAUSE_114,
            NoticeType.SHOW_CAUSE_122,
            NoticeType.SHOW_CAUSE_161,
            NoticeType.SHOW_CAUSE_GENERAL,
            NoticeType.ASSESSMENT_120,
            NoticeType.ASSESSMENT_121,
            NoticeType.ASSESSMENT_122,
            NoticeType.PROVISIONAL_ASSESSMENT,
            NoticeType.BEST_JUDGMENT,
            NoticeType.AMENDED_ASSESSMENT,
            NoticeType.DEMAND_137,
            NoticeType.RECOVERY_138,
            NoticeType.ARREARS_NOTICE,
            NoticeType.PENALTY_182,
            NoticeType.PENALTY_184,
            NoticeType.PENALTY_GENERAL,
            NoticeType.AUDIT_214C,
        }:
            return AppealGuide(
                notice_type=notice_type.value,
                forum=AppealForum.CIR_A.value,
                time_limit_days=30,
                is_appealable=is_appealable,
                forms_required=["Form-31 (Memorandum of Appeal)"],
                documents_needed=[
                    "Original notice/order copy",
                    "Your response filed (if any)",
                    "Copies of evidence relied upon",
                    "Power of attorney (if through representative)",
                    "Statement of facts",
                    "Grounds of appeal",
                ],
                fees_required="PKR 1,000 (or as per latest SRO)",
                common_grounds=[
                    "Notice not properly served",
                    "Order passed without affording hearing",
                    "No proper evidence considered",
                    "Misinterpretation of law",
                    "Findings against facts on record",
                    "Penalty quantum excessive",
                    "Procedural irregularities",
                ],
                success_factors=[
                    "Strong documentary evidence",
                    "Clear legal grounds",
                    "Consistent stance throughout",
                    "Professional representation",
                    "Timely filing",
                ],
                typical_success_rate="40-60% (partial relief common)",
                estimated_cost="PKR 50,000-200,000 (including professional fees)",
                notes=[
                    "File appeal within 30 days of order",
                    "Pay prescribed fee (challan)",
                    "Submit 3 copies + 1 for office",
                    "Attach certified copies of order",
                ],
            )

        # Audit/Enquiry notices - usually not directly appealable but
        # order arising from them is
        elif notice_type in {
            NoticeType.AUDIT_SELECTION,
            NoticeType.ENQUIRY_176,
            NoticeType.SURVEY,
            NoticeType.INFORMATION_REQUEST,
            NoticeType.COMPLIANCE_NOTICE,
        }:
            return AppealGuide(
                notice_type=notice_type.value,
                forum="not_directly_appealable",
                time_limit_days=0,
                is_appealable=is_appealable,
                forms_required=[],
                documents_needed=["Notice copy"],
                fees_required="N/A",
                common_grounds=[],
                success_factors=[],
                typical_success_rate="N/A",
                estimated_cost="PKR 0",
                notes=[
                    "These notices are not directly appealable",
                    "You must respond/comply",
                    "If adverse order arises from these, THAT order is appealable",
                ],
            )

        # Intimation/rectification
        elif notice_type in {
            NoticeType.INTIMATION_143,
            NoticeType.RECTIFICATION,
            NoticeType.AMENDMENT,
        }:
            return AppealGuide(
                notice_type=notice_type.value,
                forum=AppealForum.CIR_A.value,
                time_limit_days=30,
                is_appealable=is_appealable,
                forms_required=["Form-31"],
                documents_needed=["Intimation copy", "Relevant return/record"],
                fees_required="PKR 1,000",
                common_grounds=[
                    "Computation error",
                    "Wrong data considered",
                    "Procedural lapse",
                ],
                success_factors=[
                    "Clear math error evident",
                    "Documentation of correct position",
                ],
                typical_success_rate="60-70%",
                estimated_cost="PKR 30,000-100,000",
                notes=["File rectification if just arithmetic error"],
            )

        # Prosecution - serious
        elif notice_type == NoticeType.PROSECUTION:
            return AppealGuide(
                notice_type=notice_type.value,
                forum="special_court",
                time_limit_days=14,
                is_appealable=is_appealable,
                forms_required=["Bail application (urgent)"],
                documents_needed=[
                    "Notice copy",
                    "All relevant tax records",
                    "Identity documents",
                ],
                fees_required="Court fees + legal fees",
                common_grounds=[
                    "No willful default",
                    "Reasonable cause for non-compliance",
                    "Settlement of underlying liability",
                ],
                success_factors=[
                    "Immediate engagement of criminal lawyer",
                    "Settlement of dues before hearing",
                    "Demonstrating cooperation",
                ],
                typical_success_rate="Varies (settlement recommended)",
                estimated_cost="PKR 200,000-500,000+",
                notes=[
                    "URGENT: Engage criminal lawyer immediately",
                    "Consider settlement to avoid prosecution",
                ],
            )

        # Default - no specific appeal
        return AppealGuide(
            notice_type=notice_type.value,
            forum="consult_professional",
            time_limit_days=0,
            is_appealable=is_appealable,
            forms_required=[],
            documents_needed=["Notice copy"],
            fees_required="N/A",
            common_grounds=[],
            success_factors=[],
            typical_success_rate="N/A",
            estimated_cost="N/A",
            notes=[
                "Consult a tax professional for this notice type",
                "Check if underlying order is appealable",
            ],
        )

    @staticmethod
    def format_guide(guide: AppealGuide) -> str:
        """Format appeal guide."""
        lines = [
            "=== Appeal Guide ===",
            f"Notice Type: {guide.notice_type}",
            "",
            f"Appealable: {'Yes' if guide.is_appealable else 'No'}",
            f"Forum: {guide.forum}",
            f"Time Limit: {guide.time_limit_days} days from order",
            f"Fees: {guide.fees_required}",
            f"Estimated Cost: {guide.estimated_cost}",
            f"Typical Success Rate: {guide.typical_success_rate}",
            "",
        ]

        if guide.forms_required:
            lines.append("--- Forms Required ---")
            for form in guide.forms_required:
                lines.append(f"  📋 {form}")

        if guide.documents_needed:
            lines.append("\n--- Documents Needed ---")
            for doc in guide.documents_needed:
                lines.append(f"  📎 {doc}")

        if guide.common_grounds:
            lines.append("\n--- Common Grounds for Appeal ---")
            for ground in guide.common_grounds:
                lines.append(f"  • {ground}")

        if guide.success_factors:
            lines.append("\n--- Success Factors ---")
            for factor in guide.success_factors:
                lines.append(f"  ✓ {factor}")

        if guide.notes:
            lines.append("\n--- Important Notes ---")
            for note in guide.notes:
                lines.append(f"  ⚠️  {note}")

        return "\n".join(lines)

"""
Notice Analyzer - Main Orchestrator
====================================

Unified entry point for all notice analysis operations.

Workflow:
1. Take notice text (from PDF/Image OCR or manual input)
2. Classify notice type
3. Extract key information
4. Calculate deadline
5. Generate action plan
6. Generate appeal guide
7. Return comprehensive analysis
"""

import logging
import uuid
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.notice_analyzer.classifier import NoticeClassifier, ClassificationResult
from app.notice_analyzer.extractor import NoticeExtractor, ExtractedInfo
from app.notice_analyzer.deadline import DeadlineCalculator, DeadlineInfo
from app.notice_analyzer.action_plan import ActionPlanGenerator, ActionPlan
from app.notice_analyzer.appeal_guide import AppealGuideGenerator, AppealGuide

logger = logging.getLogger("notice_analyzer")

# Audit log is capped so the long-lived analyzer singleton cannot grow forever
AUDIT_LOG_MAX_ENTRIES = 1000


@dataclass
class NoticeAnalysis:
    """Complete notice analysis result."""
    analysis_id: str
    timestamp: str
    duration_ms: float

    # Classification
    notice_type: str
    confidence: float
    is_critical: bool
    is_appealable: bool

    # Extracted info
    taxpayer_name: Optional[str] = None
    taxpayer_ntn: Optional[str] = None
    notice_id: Optional[str] = None
    issue_date: Optional[str] = None
    tax_years: list[str] = field(default_factory=list)
    sections_cited: list[str] = field(default_factory=list)
    total_demanded: Optional[float] = None
    tax_amount: Optional[float] = None
    penalty_amount: Optional[float] = None

    # Deadline
    deadline_date: Optional[str] = None
    days_remaining: Optional[int] = None
    urgency_level: str = "unknown"

    # Plan and guide
    action_plan: Optional[ActionPlan] = None
    appeal_guide: Optional[AppealGuide] = None

    # Formatted output
    formatted_text: str = ""
    summary: str = ""


class NoticeAnalyzer:
    """Production-grade unified notice analyzer."""

    def __init__(self):
        self.audit_log: deque[dict] = deque(maxlen=AUDIT_LOG_MAX_ENTRIES)

    def analyze(self, text: str) -> NoticeAnalysis:
        """
        Perform complete notice analysis.

        Args:
            text: Notice text (extracted from PDF/Image)

        Returns:
            NoticeAnalysis with all components
        """
        start_time = time.time()
        analysis_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # Step 1: Classify
        classification = NoticeClassifier.classify(text)
        logger.info(
            f"Analysis {analysis_id[:8]}: classified as "
            f"{classification.notice_type.value} "
            f"(confidence: {classification.confidence})"
        )

        # Step 2: Extract info
        extracted = NoticeExtractor.extract(text)

        # Step 3: Calculate deadline
        # The deadline comes only from a response date the notice actually
        # states; an unstated deadline is reported as unknown, never guessed.
        deadline_info = DeadlineCalculator.calculate(
            classification.notice_type,
            extracted.issue_date,
            extracted.deadline,
        )

        # Step 4: Generate action plan
        action_plan = ActionPlanGenerator.generate(classification.notice_type)

        # Step 5: Generate appeal guide
        appeal_guide = AppealGuideGenerator.generate(classification.notice_type)

        # Step 6: Build summary
        summary = self._build_summary(classification, extracted, deadline_info)

        # Build formatted text
        formatted = self._format_full_analysis(
            classification, extracted, deadline_info, action_plan, appeal_guide
        )

        duration_ms = (time.time() - start_time) * 1000

        # Log to audit
        self.audit_log.append({
            "analysis_id": analysis_id,
            "timestamp": timestamp,
            "notice_type": classification.notice_type.value,
            "confidence": classification.confidence,
            "duration_ms": round(duration_ms, 3),
        })

        return NoticeAnalysis(
            analysis_id=analysis_id,
            timestamp=timestamp,
            duration_ms=round(duration_ms, 3),
            notice_type=classification.notice_type.value,
            confidence=classification.confidence,
            is_critical=classification.is_critical,
            is_appealable=classification.is_appealable,
            taxpayer_name=extracted.taxpayer_name,
            taxpayer_ntn=extracted.taxpayer_ntn,
            notice_id=extracted.notice_id,
            issue_date=extracted.issue_date,
            tax_years=extracted.tax_years,
            sections_cited=extracted.sections_cited,
            total_demanded=extracted.total_demanded,
            tax_amount=extracted.tax_amount,
            penalty_amount=extracted.penalty_amount,
            deadline_date=deadline_info.deadline_date,
            days_remaining=deadline_info.days_remaining,
            urgency_level=deadline_info.urgency_level,
            action_plan=action_plan,
            appeal_guide=appeal_guide,
            formatted_text=formatted,
            summary=summary,
        )

    def _build_summary(
        self,
        classification: ClassificationResult,
        extracted: ExtractedInfo,
        deadline_info: DeadlineInfo,
    ) -> str:
        """Build concise summary."""
        parts = []

        # Critical/urgency
        if classification.is_critical:
            parts.append(f"⚠️  CRITICAL: {classification.notice_type.value}")

        # Classification
        confidence_pct = int(classification.confidence * 100)
        parts.append(
            f"This is a {classification.notice_type.value.replace('_', ' ').title()} "
            f"({confidence_pct}% confidence)"
        )

        # Extracted info
        if extracted.total_demanded:
            parts.append(f"Total demand: PKR {extracted.total_demanded:,.2f}")
        if extracted.tax_years:
            parts.append(f"Tax years: {', '.join(extracted.tax_years[:3])}")
        if extracted.sections_cited:
            parts.append(f"Sections cited: {', '.join(extracted.sections_cited[:5])}")

        # Deadline
        if deadline_info.days_remaining is not None:
            if deadline_info.is_overdue:
                parts.append(
                    f"⚠️  DEADLINE PASSED: Was due {deadline_info.deadline_date}"
                )
            elif deadline_info.days_remaining <= 3:
                parts.append(
                    f"🚨 URGENT: Only {deadline_info.days_remaining} days left!"
                )
            else:
                parts.append(
                    f"Deadline: {deadline_info.deadline_date} ({deadline_info.days_remaining} days)"
                )
        else:
            parts.append(
                "Deadline: not stated in notice - deadline could not be determined"
            )

        # Appealable
        if classification.is_appealable:
            parts.append("✓ Appealable")

        return " | ".join(parts)

    def _format_full_analysis(
        self,
        classification: ClassificationResult,
        extracted: ExtractedInfo,
        deadline_info: DeadlineInfo,
        action_plan: ActionPlan,
        appeal_guide: AppealGuide,
    ) -> str:
        """Format full analysis as readable text."""
        lines = [
            "=" * 60,
            "FBR NOTICE ANALYSIS REPORT",
            "=" * 60,
            "",
            f"Notice Type: {classification.notice_type.value}",
            f"Confidence: {int(classification.confidence * 100)}%",
            f"Critical: {'YES' if classification.is_critical else 'No'}",
            f"Appealable: {'YES' if classification.is_appealable else 'No'}",
            "",
        ]

        if classification.matched_signals:
            lines.append("Matched Signals:")
            for sig in classification.matched_signals[:5]:
                lines.append(f"  • {sig}")
            lines.append("")

        lines.append("--- Extracted Information ---")
        if extracted.taxpayer_name:
            lines.append(f"  Taxpayer Name: {extracted.taxpayer_name}")
        if extracted.taxpayer_ntn:
            lines.append(f"  NTN: {extracted.taxpayer_ntn}")
        if extracted.taxpayer_cnic:
            lines.append(f"  CNIC: {extracted.taxpayer_cnic}")
        if extracted.notice_id:
            lines.append(f"  Notice ID: {extracted.notice_id}")
        if extracted.issue_date:
            lines.append(f"  Issue Date: {extracted.issue_date}")
        if extracted.tax_years:
            lines.append(f"  Tax Years: {', '.join(extracted.tax_years)}")
        if extracted.sections_cited:
            lines.append(f"  Sections: {', '.join(extracted.sections_cited)}")
        if extracted.tax_amount:
            lines.append(f"  Tax Amount: PKR {extracted.tax_amount:,.2f}")
        if extracted.penalty_amount:
            lines.append(f"  Penalty: PKR {extracted.penalty_amount:,.2f}")
        if extracted.total_demanded:
            lines.append(f"  Total Demand: PKR {extracted.total_demanded:,.2f}")
        lines.append(f"  Extraction Quality: {int(extracted.extraction_quality * 100)}%")
        lines.append("")

        lines.append("--- Deadline Information ---")
        lines.append(f"  Issue Date: {deadline_info.issue_date or 'Unknown'}")
        lines.append(
            f"  Response Period: {deadline_info.days_given} days"
            if deadline_info.days_given is not None
            else "  Response Period: Not stated in notice"
        )
        lines.append(
            f"  Deadline: {deadline_info.deadline_date}"
            if deadline_info.deadline_date
            else "  Deadline: Unknown - not stated in notice"
        )
        if deadline_info.days_remaining is not None:
            if deadline_info.is_overdue:
                lines.append(f"  ⚠️  STATUS: OVERDUE (by {abs(deadline_info.days_remaining)} days)")
            else:
                lines.append(f"  Days Remaining: {deadline_info.days_remaining}")
        else:
            lines.append("  Days Remaining: Unknown - no deadline stated in notice")
        lines.append(f"  Urgency: {deadline_info.urgency_level.upper()}")
        lines.append(f"  Next Action: {deadline_info.next_action}")
        if deadline_info.notes:
            lines.append("  Notes:")
            for note in deadline_info.notes:
                lines.append(f"    - {note}")
        lines.append("")

        lines.append("--- Action Plan Summary ---")
        lines.append(f"  {action_plan.summary}")
        lines.append(f"  Total Steps: {action_plan.total_steps}")
        lines.append(f"  Estimated Time: {action_plan.estimated_total_hours} hours")
        lines.append(f"  Professional Help: {'Required' if action_plan.requires_professional_help else 'Optional'}")
        lines.append("")

        lines.append("--- Appeal Guide Summary ---")
        lines.append(f"  Forum: {appeal_guide.forum}")
        lines.append(f"  Time Limit: {appeal_guide.time_limit_days} days")
        if appeal_guide.is_appealable:
            lines.append(f"  Forms: {', '.join(appeal_guide.forms_required)}")
            lines.append(f"  Fees: {appeal_guide.fees_required}")
        lines.append("=" * 60)

        return "\n".join(lines)


# Singleton
_analyzer_instance: Optional[NoticeAnalyzer] = None


def get_notice_analyzer() -> NoticeAnalyzer:
    """Get singleton notice analyzer."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = NoticeAnalyzer()
    return _analyzer_instance

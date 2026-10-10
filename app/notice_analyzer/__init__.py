"""
Notice Analyzer - Production-Grade
==================================

FBR Notices/Show Cause/Orders ke liye dedicated analyzer (text input):
- Notice type classification (Show Cause, Order, Demand, Intimation, etc.)
- Key information extraction (date, amount, sections, deadline)
- Action plan generation
- Appeal guidance
- Deadline tracking (only from a deadline stated in the notice)
- Legal reference lookup

Supports the notice types listed in classifier.NoticeType; the types that
actually have classification signals are reported by
classifier.get_notice_type_catalog().
"""

from app.notice_analyzer.classifier import NoticeClassifier, NoticeType
from app.notice_analyzer.extractor import NoticeExtractor, ExtractedInfo
from app.notice_analyzer.action_plan import ActionPlanGenerator, ActionPlan
from app.notice_analyzer.appeal_guide import AppealGuideGenerator, AppealGuide
from app.notice_analyzer.analyzer import NoticeAnalyzer, get_notice_analyzer
from app.notice_analyzer.deadline import DeadlineCalculator, DeadlineInfo

__all__ = [
    "NoticeClassifier",
    "NoticeType",
    "NoticeExtractor",
    "ExtractedInfo",
    "ActionPlanGenerator",
    "ActionPlan",
    "AppealGuideGenerator",
    "AppealGuide",
    "NoticeAnalyzer",
    "DeadlineCalculator",
    "DeadlineInfo",
    "get_notice_analyzer",
]

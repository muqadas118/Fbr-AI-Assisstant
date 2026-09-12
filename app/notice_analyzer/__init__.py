"""
Notice Analyzer - Production-Grade
===================================

FBR Notices/Show Cause/Orders ke liye dedicated analyzer:
- PDF/Image upload
- OCR extraction (text from image-based PDFs)
- Notice type classification (Show Cause, Order, Demand, Intimation, etc.)
- Key information extraction (date, amount, sections, deadline)
- Action plan generation
- Appeal guidance
- Deadline tracking
- Legal reference lookup

Supports 30+ FBR notice types with full workflow.
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

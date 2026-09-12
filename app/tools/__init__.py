"""
FBR Tool Engine — reusable tools over EXISTING capabilities.

This package exposes the project's reusable tools and a default
registry containing all 13 stable-named tools:

    rag_search, hybrid_search, metadata_filter, rule_engine,
    calculation_engine, document_parser, duplicate_detection,
    similarity_engine, anomaly_detection, web_research,
    notification, report_generator, tax_optimization

Every tool is a thin, validated wrapper around an existing
implementation (RAG engine, hybrid retriever, vector metadata,
calculation agent logic, extraction pipeline, daily-update fetch
layer). Nothing is duplicated and no arbitrary code execution is
possible: the registry only runs registered tool instances with
plain validated data.

All heavy resources load lazily inside execute(), so building
the registry is cheap.
"""

from app.tools.base import BaseTool, ToolError, ToolResult
from app.tools.document_tools import (
    AnomalyDetectionTool,
    DocumentParserTool,
    DuplicateDetectionTool,
    SimilarityEngineTool,
)
from app.tools.knowledge_tools import (
    CalculationEngineTool,
    RuleEngineTool,
)
from app.tools.output_tools import NotificationTool, ReportGeneratorTool
from app.tools.registry import ToolRegistry
from app.tools.search_tools import (
    HybridSearchTool,
    MetadataFilterTool,
    RAGSearchTool,
)
from app.tools.tax_optimization import TaxOptimizationTool
from app.tools.web_tools import WebResearchTool

ALL_TOOL_CLASSES = (
    RAGSearchTool,
    HybridSearchTool,
    MetadataFilterTool,
    RuleEngineTool,
    CalculationEngineTool,
    DocumentParserTool,
    DuplicateDetectionTool,
    SimilarityEngineTool,
    AnomalyDetectionTool,
    WebResearchTool,
    NotificationTool,
    ReportGeneratorTool,
    TaxOptimizationTool,
)

TOOL_NAMES = tuple(tool.name for tool in ALL_TOOL_CLASSES)


def build_default_registry() -> ToolRegistry:
    """Build a registry with all 13 project tools registered."""

    registry = ToolRegistry()

    for tool_class in ALL_TOOL_CLASSES:
        registry.register(tool_class())

    return registry


DEFAULT_REGISTRY = build_default_registry()


def get_default_registry() -> ToolRegistry:
    """Return the process-wide default tool registry."""

    return DEFAULT_REGISTRY

"""
Sales Tax Agent (Phase 9).

Scope:
- Sales Tax Act 1990
- sales tax registration
- returns
- input/output tax
- invoices
- exemptions
- penalties and compliance
- relevant Finance Act amendments affecting sales tax

Query expansion: none required. The existing RAG retrieval
already resolves sales-tax queries with high precision; the
canonical keyword signals ("sales tax", "input tax",
"output tax") are strong retrieval anchors.
"""

from __future__ import annotations

from app.agents.base import SpecializedAgent


class SalesTaxAgent(SpecializedAgent):
    domain = "sales_tax"

    TOOLS = (
        "rag_search",
        "hybrid_search",
        "metadata_filter",
        "rule_engine",
        "calculation_engine",
    )

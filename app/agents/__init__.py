"""
Phase 9 (corrected): 9-Agent FBR Architecture + Deterministic Router.

Public API:
- FBRQueryRouter / RoutingDecision / route_query
- SpecializedAgent
- IncomeTaxAgent, SalesTaxAgent, FederalExciseAgent,
  CustomsAgent, RegistrationAgent, ReturnFilingAgent,
  CalculationAgent, NoticeAppealAgent, ResearchAgent
- AgentOrchestrator

Removed: PropertyValuationAgent, FinanceActAgent, GeneralFBRAgent.
"""

from app.agents.base import SpecializedAgent
from app.agents.calculation_agent import CalculationAgent
from app.agents.customs_agent import CustomsAgent
from app.agents.federal_excise_agent import FederalExciseAgent
from app.agents.income_tax_agent import IncomeTaxAgent
from app.agents.notice_appeal_agent import NoticeAppealAgent
from app.agents.orchestrator import AgentOrchestrator
from app.agents.registration_agent import RegistrationAgent
from app.agents.research_agent import ResearchAgent
from app.agents.return_filing_agent import ReturnFilingAgent
from app.agents.router import (
    DOMAIN_PRIORITY,
    FBRQueryRouter,
    RoutingDecision,
    route_query,
)
from app.agents.sales_tax_agent import SalesTaxAgent

__all__ = [
    "DOMAIN_PRIORITY",
    "FBRQueryRouter",
    "RoutingDecision",
    "route_query",
    "SpecializedAgent",
    "IncomeTaxAgent",
    "SalesTaxAgent",
    "FederalExciseAgent",
    "CustomsAgent",
    "RegistrationAgent",
    "ReturnFilingAgent",
    "CalculationAgent",
    "NoticeAppealAgent",
    "ResearchAgent",
    "AgentOrchestrator",
]

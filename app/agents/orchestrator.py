"""
Agent Orchestrator (Phase 9 corrected, 9-agent architecture).

Composes the deterministic router with the specialized agents:

    User Query
      -> FBRQueryRouter.route()
      -> one or more SpecializedAgent.handle()
      -> existing FBRRAGEngine (retrieval + LLM + verification)
      -> grounded answer / safe refusal

Single-domain queries run exactly one agent (no unnecessary
multi-agent execution). Multi-domain queries run every routed
agent and combine their INDEPENDENTLY VERIFIED results:

- Each domain answer is produced and verified by the existing
  Phase 7/8 pipeline on its own.
- The combined answer only ever concatenates per-domain answers
  that are either grounded or the deterministic safe refusal
  placeholder. No cross-domain content is merged, invented, or
  re-worded.
- The overall `grounded` flag for a multi-domain response is
  True only when EVERY routed domain is grounded; per-domain
  flags remain visible in `domain_results`.
- Aggregate sources are deduplicated by chunk_id and keep the
  full provenance record from the RAG engine.

All agents share ONE FBRRAGEngine instance (one FAISS load, one
BM25 index, one embedding model) — no per-agent vector store.

9 required agents:

  1. IncomeTaxAgent       (income_tax)
  2. SalesTaxAgent        (sales_tax)
  3. FederalExciseAgent   (federal_excise)
  4. CustomsAgent         (customs)
  5. RegistrationAgent    (registration)
  6. ReturnFilingAgent    (return_filing)
  7. CalculationAgent     (calculation)
  8. NoticeAppealAgent    (notice_appeal)
  9. ResearchAgent        (research)

No PropertyValuationAgent, FinanceActAgent, or GeneralFBRAgent
exists in this architecture.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.agents.base import SpecializedAgent
from app.agents.calculation_agent import CalculationAgent
from app.agents.customs_agent import CustomsAgent
from app.agents.federal_excise_agent import FederalExciseAgent
from app.agents.income_tax_agent import IncomeTaxAgent
from app.agents.notice_appeal_agent import NoticeAppealAgent
from app.agents.registration_agent import RegistrationAgent
from app.agents.research_agent import ResearchAgent
from app.agents.return_filing_agent import ReturnFilingAgent
from app.agents.router import FBRQueryRouter, RoutingDecision
from app.agents.sales_tax_agent import SalesTaxAgent
from app.rag_engine import DEFAULT_TOP_K, _NO_EVIDENCE_ANSWER
from app.verification_layer import PLACEHOLDER_ANSWER

_AGENT_CLASSES: dict[str, type[SpecializedAgent]] = {
    "income_tax": IncomeTaxAgent,
    "sales_tax": SalesTaxAgent,
    "federal_excise": FederalExciseAgent,
    "customs": CustomsAgent,
    "registration": RegistrationAgent,
    "return_filing": ReturnFilingAgent,
    "calculation": CalculationAgent,
    "notice_appeal": NoticeAppealAgent,
    "research": ResearchAgent,
}

_SAFE_ANSWERS = (PLACEHOLDER_ANSWER, _NO_EVIDENCE_ANSWER)


class AgentOrchestrator:
    """
    Deterministic router + 9-agent orchestrator.
    """

    def __init__(
        self,
        rag_engine: Any | None = None,
        router: FBRQueryRouter | None = None,
    ):
        self._rag_engine = rag_engine
        self.router = router or FBRQueryRouter()
        self._agents: dict[str, SpecializedAgent] | None = None

    @property
    def rag_engine(self):
        if self._rag_engine is None:
            from app.rag_engine import FBRRAGEngine

            self._rag_engine = FBRRAGEngine()
        return self._rag_engine

    @property
    def agents(self) -> dict[str, SpecializedAgent]:
        """
        All 9 agents sharing one RAG engine instance.
        """

        if self._agents is None:
            engine = self.rag_engine
            self._agents = {
                domain: cls(rag_engine=engine)
                for domain, cls in _AGENT_CLASSES.items()
            }
        return self._agents

    def route(self, question: object) -> RoutingDecision:
        return self.router.route(question)

    def handle(
        self,
        question: object,
        top_k: int = DEFAULT_TOP_K,
    ) -> dict:
        """
        Route the question and run the selected agent(s).

        Returns a dict with:
        - question, domains, primary_domain, multi_domain
        - routing (RoutingDecision.to_dict())
        - domain_results (list of per-agent responses)
        - answer, sources, verification, grounded
          (single-domain: the agent's canonical RAG fields,
           unchanged; multi-domain: safely combined as described
           in the module docstring)
        """

        decision = self.router.route(question)
        domains = decision.domains

        if len(domains) == 1:
            results = [self.agents[domains[0]].handle(question, top_k=top_k)]
        else:
            # Multi-domain agents are independent (they share one
            # read-only RAG engine), so run them in parallel. This
            # halves latency for 2-domain queries instead of paying
            # one full LLM round-trip per domain sequentially.
            agents = self.agents
            with ThreadPoolExecutor(
                max_workers=min(len(domains), 4)
            ) as pool:
                results = list(
                    pool.map(
                        lambda domain: agents[domain].handle(
                            question, top_k=top_k
                        ),
                        domains,
                    )
                )

        if len(results) == 1:
            only = results[0]
            return {
                "question": only["question"],
                "domains": list(domains),
                "primary_domain": decision.primary_domain,
                "multi_domain": False,
                "routing": decision.to_dict(),
                "domain_results": results,
                "answer": only["answer"],
                "sources": only["sources"],
                "verification": only["verification"],
                "grounded": only["grounded"],
            }

        combined_parts: list[str] = []
        aggregate_sources: list[dict] = []
        seen_chunk_ids: set[str] = set()
        seen_answers: list[tuple[str, str, set[str]]] = []  # (normalized, label, numbers)

        def _numbers(text: str) -> set[str]:
            from app.verification_answer import extract_numeric_claims

            return {n.replace(",", "") for n in extract_numeric_claims(str(text))}

        def _is_repetition(answer: str) -> str | None:
            """Return the first label whose answer is effectively the same.

            Two routed domains restating the same verified fact is
            repetition, not new information. Treat answers as the same
            when they are near-identical AND carry the same numbers, so
            a genuinely different figure in another domain is never
            suppressed. No claims are merged or re-worded.
            """
            from difflib import SequenceMatcher

            norm = " ".join(str(answer).lower().split())
            nums = _numbers(answer)
            for prev_norm, prev_label, prev_nums in seen_answers:
                if nums == prev_nums and SequenceMatcher(
                    None, norm, prev_norm
                ).ratio() >= 0.90:
                    return prev_label
            return None

        for result in results:
            label = result["domain"].replace("_", " ").title()
            answer = result["answer"]
            if answer in _SAFE_ANSWERS:
                combined_parts.append(
                    f"[{label}] {_NO_EVIDENCE_ANSWER}"
                )
                continue
            first_label = _is_repetition(answer)
            if first_label is not None:
                combined_parts.append(
                    f"[{label}] (Same answer as [{first_label}]; "
                    "omitted to avoid repetition.)"
                )
            else:
                seen_answers.append(
                    (" ".join(str(answer).lower().split()), label, _numbers(answer))
                )
                combined_parts.append(f"[{label}] {answer}")

            for source in result["sources"]:
                chunk_id = str(source.get("chunk_id") or "")
                key = chunk_id or f"idx:{len(aggregate_sources)}"
                if key in seen_chunk_ids:
                    continue
                seen_chunk_ids.add(key)
                aggregate_sources.append(source)

        grounded = all(bool(r["grounded"]) for r in results)

        verification = {
            "passed": grounded,
            "reason": (
                f"Multi-domain response: "
                f"{sum(1 for r in results if r['grounded'])}"
                f"/{len(results)} routed domains grounded. Each "
                f"domain answer was independently verified by the "
                f"canonical RAG verification pipeline."
            ),
            "failed_checks": [
                f"{r['domain']}:unverified"
                for r in results
                if not r["grounded"]
            ],
            "checks": {
                r["domain"]: bool(r["grounded"]) for r in results
            },
            "per_domain": [r["verification"] for r in results],
        }

        return {
            "question": str(question) if question is not None else "",
            "domains": list(domains),
            "primary_domain": decision.primary_domain,
            "multi_domain": True,
            "routing": decision.to_dict(),
            "domain_results": results,
            "answer": "\n\n".join(combined_parts),
            "sources": aggregate_sources,
            "verification": verification,
            "grounded": grounded,
        }

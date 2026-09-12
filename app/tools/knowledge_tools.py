"""
Knowledge tools.

- rule_engine:        controlled evaluation of declarative tax /
                      compliance rules loaded from rules.json.
                      Whitelisted comparison operators only — no
                      eval(), no arbitrary code execution. Seed
                      rules carry corpus provenance (document,
                      section, sha256).
- calculation_engine: exposes the EXISTING Calculation Agent
                      logic (app.agents.calculation_agent.
                      _extract_calculation) as a reusable tool.
                      Deterministic arithmetic only — the agent
                      remains responsible for RAG grounding and
                      verification of the underlying rate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolError

RULES_PATH = Path(__file__).resolve().parent / "rules.json"

_MAX_FACTS = 50
_MAX_CALC_TEXT = 1000
_MAX_NUMERIC = 10**15

# Whitelisted condition operators. Evaluating a rule is a pure
# data comparison — never dynamic code execution.
_OPERATORS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: _both_numeric(a, b) and a > b,
    "gte": lambda a, b: _both_numeric(a, b) and a >= b,
    "lt": lambda a, b: _both_numeric(a, b) and a < b,
    "lte": lambda a, b: _both_numeric(a, b) and a <= b,
    "in": lambda a, b: isinstance(b, (list, tuple)) and a in b,
    "contains": lambda a, b: (
        isinstance(a, str) and isinstance(b, str) and b.lower() in a.lower()
    ),
}


def _both_numeric(a: Any, b: Any) -> bool:
    return (
        isinstance(a, (int, float))
        and not isinstance(a, bool)
        and isinstance(b, (int, float))
        and not isinstance(b, bool)
    )


_loaded_rules: list[dict] | None = None


def _load_rules() -> list[dict]:
    """Load and schema-validate rules from rules.json (cached)."""

    global _loaded_rules

    if _loaded_rules is not None:
        return _loaded_rules

    if not RULES_PATH.exists():
        raise ToolError("Rule data file is not available.")

    try:
        with open(RULES_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ToolError(f"Rule data file could not be read: {error}")

    rules = data.get("rules") if isinstance(data, dict) else None

    if not isinstance(rules, list):
        raise ToolError("Rule data file must contain a 'rules' list.")

    for rule in rules:
        if not isinstance(rule, dict):
            raise ToolError("Each rule must be a JSON object.")
        for field in ("id", "name", "domain", "when", "then"):
            if field not in rule:
                raise ToolError(
                    f"Rule is missing required field '{field}'."
                )
        if not isinstance(rule["when"], list) or not rule["when"]:
            raise ToolError(
                f"Rule '{rule['id']}' must have a non-empty 'when' list."
            )
        for condition in rule["when"]:
            if not isinstance(condition, dict):
                raise ToolError(
                    f"Rule '{rule['id']}' has a malformed condition."
                )
            if condition.get("op") not in _OPERATORS:
                raise ToolError(
                    f"Rule '{rule['id']}' uses unsupported operator "
                    f"'{condition.get('op')}'."
                )
        if not isinstance(rule["then"], dict):
            raise ToolError(
                f"Rule '{rule['id']}' must have a 'then' object."
            )

    _loaded_rules = rules
    return _loaded_rules


def evaluate_rules(
    facts: dict,
    rules: list[dict],
    domain: str | None = None,
) -> list[dict]:
    """
    Evaluate declarative rules against a fact set.

    A rule matches when EVERY condition matches (AND). Operator
    semantics are fixed by the whitelist above.
    """

    matched = []

    for rule in rules:
        if domain and rule.get("domain") != domain:
            continue

        conditions_met = True

        for condition in rule["when"]:
            field = condition.get("field")
            op = condition.get("op")
            expected = condition.get("value")

            if field not in facts:
                conditions_met = False
                break

            operator = _OPERATORS.get(op)

            if operator is None or not operator(
                facts[field], expected
            ):
                conditions_met = False
                break

        if conditions_met:
            matched.append(
                {
                    "id": rule["id"],
                    "name": rule["name"],
                    "domain": rule["domain"],
                    "outcome": rule["then"],
                    "source": rule.get("source"),
                }
            )

    matched.sort(key=lambda m: str(m.get("id", "")))

    return matched


# ============================================================
# RULE ENGINE TOOL
# ============================================================

class RuleEngineTool(BaseTool):
    name = "rule_engine"
    description = (
        "Controlled evaluation of declarative tax/compliance rules "
        "against a fact set. Whitelisted comparison operators only "
        "(eq, ne, gt, gte, lt, lte, in, contains) — no arbitrary "
        "code execution. Rules are loaded from app/tools/rules.json "
        "and carry corpus provenance. Input: {facts: dict, "
        "domain?: str}. Returns matched rule outcomes."
    )

    def validate_input(self, payload: dict) -> dict:
        facts = payload.get("facts")

        if not isinstance(facts, dict) or not facts:
            raise ToolError("'facts' must be a non-empty JSON object.")

        if len(facts) > _MAX_FACTS:
            raise ToolError(
                f"'facts' must not exceed {_MAX_FACTS} entries."
            )

        for key, value in facts.items():
            if not isinstance(key, str) or not key:
                raise ToolError("Fact keys must be non-empty strings.")

            if isinstance(value, float) and (
                value != value or value in (float("inf"), float("-inf"))
            ):
                raise ToolError("Fact values must be finite numbers.")

            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and abs(value) > _MAX_NUMERIC
            ):
                raise ToolError("Fact numeric values are out of range.")

        domain = payload.get("domain")

        if domain is not None and (
            not isinstance(domain, str) or not domain.strip()
        ):
            raise ToolError("'domain' must be a non-empty string.")

        return {
            "facts": facts,
            "domain": domain.strip() if domain else None,
        }

    def execute(self, payload: dict) -> Any:
        rules = _load_rules()

        matched = evaluate_rules(
            payload["facts"],
            rules,
            domain=payload["domain"],
        )

        return {
            "matched": matched,
            "matched_count": len(matched),
            "rules_evaluated": len(rules),
        }


# ============================================================
# CALCULATION ENGINE TOOL
# ============================================================

class CalculationEngineTool(BaseTool):
    name = "calculation_engine"
    description = (
        "Deterministic percentage-of-amount calculation reusing the "
        "EXISTING Calculation Agent extraction logic. Input either "
        "{question: str} (free-form, e.g. 'calculate 10% tax on "
        "500000') or {amount: number, percent: number}. Returns "
        "inputs, steps (expression) and result. The calling agent "
        "remains responsible for grounding the rate in verified "
        "corpus evidence."
    )

    def validate_input(self, payload: dict) -> dict:
        question = payload.get("question")
        amount = payload.get("amount")
        percent = payload.get("percent")

        has_question = question is not None
        has_pair = amount is not None or percent is not None

        if has_question and has_pair:
            raise ToolError(
                "Provide either 'question' or 'amount'+'percent', "
                "not both."
            )

        if has_question:
            if not isinstance(question, str) or not question.strip():
                raise ToolError("'question' must be a non-empty string.")

            if len(question) > _MAX_CALC_TEXT:
                raise ToolError(
                    f"'question' must not exceed {_MAX_CALC_TEXT} "
                    "characters."
                )

            return {"mode": "question", "question": question.strip()}

        if amount is None or percent is None:
            raise ToolError(
                "Provide 'question' or both 'amount' and 'percent'."
            )

        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ToolError("'amount' must be a number.")

        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            raise ToolError("'percent' must be a number.")

        if not (0 < amount <= _MAX_NUMERIC):
            raise ToolError("'amount' must be a positive number.")

        if not (0 < percent <= 1000):
            raise ToolError("'percent' must be between 0 and 1000.")

        return {
            "mode": "explicit",
            "amount": float(amount),
            "percent": float(percent),
        }

    def execute(self, payload: dict) -> Any:
        if payload["mode"] == "explicit":
            amount = payload["amount"]
            percent = payload["percent"]
            result = round(amount * percent / 100.0, 2)

            return {
                "kind": "percent_of_amount",
                "percent": percent,
                "amount": amount,
                "expression": (
                    f"{amount} x {percent}% = {result}"
                ),
                "result": result,
                "computed": True,
            }

        # Reuse the EXISTING Calculation Agent extraction logic.
        from app.agents.calculation_agent import _extract_calculation

        calc = _extract_calculation(payload["question"])

        if calc is None:
            return {
                "kind": None,
                "calculation": None,
                "computed": False,
                "reason": (
                    "No deterministic (amount, percent) pair could be "
                    "extracted from the question."
                ),
            }

        return {
            "kind": calc["kind"],
            "calculation": calc,
            "computed": True,
        }

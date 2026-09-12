"""
Tool Engine foundation.

A tool is a REUSABLE, validated wrapper around an EXISTING project
capability. Tools never contain new retrieval, embedding, vector
database, verification, or LLM logic — they delegate to the
canonical implementations (FBRRAGEngine, FBRHybridRetriever,
CalculationAgent logic, the extraction pipeline, the daily-update
fetch layer, and vector metadata).

Contract for every tool:

- stable name (registry key)
- description
- validated input (explicit checks, ToolError on invalid input)
- structured output (ToolResult)
- error handling (run() never raises; failures return ok=False)

There is NO arbitrary code execution: the registry only executes
registered tool instances, and tool inputs are plain validated
data — never Python source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ToolError(ValueError):
    """
    Raised for invalid tool input or a controlled tool failure.
    Tool internals must raise this for expected failures; any
    unexpected exception is captured by run() and reported as a
    failed ToolResult without leaking internal details.
    """


@dataclass
class ToolResult:
    """Structured, JSON-serializable outcome of one tool run."""

    tool: str
    ok: bool
    data: Any = None
    error: str | None = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "meta": self.meta,
        }


class BaseTool:
    """
    Base class for all reusable tools.

    Subclasses implement:

    - name / description (stable class attributes)
    - validate_input(payload) -> cleaned payload (raise ToolError)
    - execute(clean_payload) -> structured data (raise ToolError
      for controlled failures)
    """

    name: str = ""
    description: str = ""

    def validate_input(self, payload: dict) -> dict:
        raise NotImplementedError

    def execute(self, payload: dict) -> Any:
        raise NotImplementedError

    def run(self, payload: dict | None = None) -> ToolResult:
        """
        Validate then execute. NEVER raises: every failure mode is
        returned as a structured ToolResult with ok=False and a
        safe message (no internal paths, no stack traces).
        """

        if payload is None:
            payload = {}

        if not isinstance(payload, dict):
            return ToolResult(
                tool=self.name,
                ok=False,
                error="Tool input must be a JSON object.",
            )

        try:
            clean = self.validate_input(payload)
        except ToolError as error:
            return ToolResult(
                tool=self.name,
                ok=False,
                error=str(error),
            )
        except Exception:
            return ToolResult(
                tool=self.name,
                ok=False,
                error="Invalid tool input.",
            )

        try:
            data = self.execute(clean)
        except ToolError as error:
            return ToolResult(
                tool=self.name,
                ok=False,
                error=str(error),
            )
        except Exception:
            return ToolResult(
                tool=self.name,
                ok=False,
                error="Tool execution failed.",
            )

        return ToolResult(tool=self.name, ok=True, data=data)

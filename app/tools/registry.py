"""
Tool Registry.

Minimal, controlled registry for the project's reusable tools.

- register(tool): add a BaseTool instance (stable name required)
- get(name): fetch a registered tool
- list_tools(): discovery (name + description)
- execute(name, payload): run a registered tool with validated
  input and return a structured ToolResult

No arbitrary execution: only registered tool instances can run,
and only with plain data payloads. Unknown names are refused.
"""

from __future__ import annotations

from app.tools.base import BaseTool, ToolError, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not isinstance(tool, BaseTool):
            raise ToolError("Only BaseTool instances can be registered.")

        name = getattr(tool, "name", "") or ""

        if not name or not isinstance(name, str):
            raise ToolError("Tool must have a non-empty string name.")

        if not getattr(tool, "description", ""):
            raise ToolError(
                f"Tool '{name}' must have a description."
            )

        if name in self._tools:
            raise ToolError(f"Tool '{name}' is already registered.")

        self._tools[name] = tool

    def get(self, name: str) -> BaseTool:
        if not isinstance(name, str) or name not in self._tools:
            raise ToolError(f"Unknown tool: {name!r}")

        return self._tools[name]

    def has(self, name: str) -> bool:
        return isinstance(name, str) and name in self._tools

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self._tools.values()
        ]

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def execute(
        self,
        name: str,
        payload: dict | None = None,
    ) -> ToolResult:
        """
        Execute a registered tool by stable name.

        Unknown tools return a failed ToolResult instead of
        raising, so callers can surface a safe error.
        """

        try:
            tool = self.get(name)
        except ToolError as error:
            return ToolResult(
                tool=name if isinstance(name, str) else "",
                ok=False,
                error=str(error),
            )

        return tool.run(payload)

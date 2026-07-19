"""Tool abstraction + registry.

Every tool exposes a typed `ToolSpec` (advertised to the LLM) and a `run` method
returning a `ToolResult`. Tools that need per-turn state (the session workspace)
receive a `RunContext`; they never take it as an LLM-supplied argument. The
`ToolRegistry` is what the agent loop talks to: it hands the model the tool specs
and dispatches calls back to implementations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.models.tools import ToolResult, ToolSpec

if TYPE_CHECKING:
    from app.models.trace import Trace


@dataclass
class RunContext:
    """Per-turn execution context handed to tools (not visible to the LLM)."""

    session_id: str
    workspace: Path  # session working dir for artifacts/notes
    trace: "Trace | None" = None  # shared trace so delegated agents nest their spans


class Tool(ABC):
    """Base class for all tools."""

    name: str
    description: str
    parameters: dict = {}

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description, parameters=self.parameters
        )

    @abstractmethod
    def run(self, ctx: RunContext, **kwargs) -> ToolResult:
        """Execute the tool. kwargs are the LLM-supplied arguments."""

    # Convenience constructors for uniform results.
    def ok(self, content: str, **extra) -> ToolResult:
        return ToolResult(tool_call_id="", name=self.name, ok=True, content=content, **extra)

    def fail(self, error: str) -> ToolResult:
        return ToolResult(
            tool_call_id="", name=self.name, ok=False, content=error, error=error
        )


class ToolRegistry:
    """Holds the available tools and dispatches calls."""

    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def specs(self) -> list[dict]:
        """OpenAI/Groq-format tool list for the chat request."""
        return [t.spec().to_openai_tool() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def run(self, name: str, ctx: RunContext, arguments: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_call_id="",
                name=name,
                ok=False,
                content=f"Unknown tool '{name}'. Available: {', '.join(self._tools)}.",
                error="unknown_tool",
            )

        # Sanitize model-supplied arguments: keep only params the tool declares and
        # drop junk keys (gpt-oss emits e.g. {"": ""} for no-arg tools). This turns
        # a first-try failure into a success instead of wasting a recovery step.
        schema = tool.parameters.get("properties", {})
        clean = {k: v for k, v in (arguments or {}).items() if k in schema}

        # Guide the model when a required argument is genuinely missing.
        required = tool.parameters.get("required", [])
        missing = [r for r in required if r not in clean or clean[r] in (None, "")]
        if missing:
            hints = "; ".join(
                f"{m}: {schema.get(m, {}).get('description', '')}" for m in missing
            )
            return ToolResult(
                tool_call_id="", name=name, ok=False,
                content=(
                    f"'{name}' is missing required argument(s): {', '.join(missing)}. "
                    f"Call it again providing — {hints}"
                ),
                error="missing_arguments",
            )

        try:
            return tool.run(ctx, **clean)
        except TypeError as exc:  # residual signature mismatch
            return ToolResult(
                tool_call_id="", name=name, ok=False,
                content=f"Invalid arguments for '{name}': {exc}", error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - tools must never crash the loop
            return ToolResult(
                tool_call_id="", name=name, ok=False,
                content=f"Tool '{name}' failed: {exc}", error=str(exc),
            )

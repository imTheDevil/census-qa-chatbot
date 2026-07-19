"""Tool boundary contracts.

`ToolCall` is what the LLM asks for; `ToolResult` is what a tool hands back. Tools
attach citations directly to their results so provenance rides along with the data
instead of being reconstructed later. `ToolSpec` is the typed description the loop
advertises to the model.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.citation import Citation


class ToolCall(BaseModel):
    """A model-requested tool invocation."""

    id: str = Field(description="Provider-assigned call id, echoed back in the result.")
    name: str = Field(description="Tool name.")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Parsed keyword arguments."
    )


class ToolResult(BaseModel):
    """The outcome of running a tool."""

    tool_call_id: str = Field(description="Matches the originating ToolCall.id.")
    name: str = Field(description="Tool name, for tracing/readability.")
    ok: bool = Field(default=True, description="False when the tool failed.")
    content: str = Field(
        default="", description="Text observation returned to the LLM."
    )
    citations: list[Citation] = Field(
        default_factory=list, description="Sources backing the returned content."
    )
    artifacts: list[str] = Field(
        default_factory=list, description="Artifact file paths produced, if any."
    )
    error: str | None = Field(default=None, description="Error summary when ok is False.")


class ToolSpec(BaseModel):
    """Typed description of a tool, rendered into the provider's tool schema."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for the tool's arguments (OpenAI/Groq tool format).",
    )

    def to_openai_tool(self) -> dict[str, Any]:
        """Serialize to the OpenAI/Groq `tools` array entry."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {"type": "object", "properties": {}},
            },
        }

"""Conversation + API contracts.

`Message` is the unit of conversation memory persisted to the filesystem.
`ChatRequest`/`AgentResponse` are the API boundary. `AgentResponse` carries the
answer plus its citations, any artifacts, and the trace id so a reviewer can see
exactly what happened.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.citation import Citation

Role = Literal["system", "user", "assistant", "tool"]


class Message(BaseModel):
    """One conversation turn entry (also mirrors provider chat-message shape)."""

    role: Role
    content: str = ""
    # Assistant turns may request tools; tool turns reference the call they answer.
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None

    def to_provider(self) -> dict[str, Any]:
        """Serialize to the OpenAI/Groq chat-message format, dropping empties."""
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


class ChatRequest(BaseModel):
    """Inbound API request."""

    session_id: str = Field(description="Stable id scoping memory + workspace.")
    message: str = Field(description="The user's message.")


class AgentResponse(BaseModel):
    """Outbound API response for one user turn."""

    session_id: str
    text: str = Field(description="Final assistant answer.")
    citations: list[Citation] = Field(default_factory=list)
    artifacts: list[str] = Field(
        default_factory=list, description="Artifact paths produced this turn."
    )
    refused: bool = Field(
        default=False,
        description="True when the system declined for lack of grounded evidence.",
    )
    trace_id: str = Field(description="Id of the persisted Trace for this turn.")

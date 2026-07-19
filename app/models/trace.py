"""Observability contracts.

A `Trace` records everything that happened while answering one user turn: each LLM
call and each tool call becomes a `Span`. The trace is persisted to the session
workspace and surfaced in the UI so a reviewer can see which calls fired and what
they returned.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

SpanKind = Literal["llm", "tool"]


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Span(BaseModel):
    """A single timed step within a turn (one LLM call or one tool call)."""

    id: str = Field(default_factory=lambda: _new_id("span"))
    kind: SpanKind
    name: str = Field(description="Model name for llm spans, tool name for tool spans.")
    agent: str = Field(default="", description="Which agent produced this span.")
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    started_at: float = Field(default_factory=time.time)
    ended_at: float | None = None
    error: str | None = None

    @property
    def duration_ms(self) -> int:
        if self.ended_at is None:
            return 0
        return int((self.ended_at - self.started_at) * 1000)

    def finish(self, output: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.output = output or {}
        self.error = error
        self.ended_at = time.time()


class Trace(BaseModel):
    """The full record of one user turn."""

    id: str = Field(default_factory=lambda: _new_id("trace"))
    session_id: str
    user_message: str
    spans: list[Span] = Field(default_factory=list)
    started_at: float = Field(default_factory=time.time)
    ended_at: float | None = None

    def start_span(self, kind: SpanKind, name: str, agent: str = "", **input_kw: Any) -> Span:
        span = Span(kind=kind, name=name, agent=agent, input=input_kw)
        self.spans.append(span)
        return span

    def finish(self) -> None:
        self.ended_at = time.time()

    @property
    def duration_ms(self) -> int:
        if self.ended_at is None:
            return 0
        return int((self.ended_at - self.started_at) * 1000)

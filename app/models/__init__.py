"""Typed contracts shared across the system.

These Pydantic models make every component boundary explicit: citations, tool
inputs/outputs, code-execution results, conversation messages, traces, and the
ingested corpus.
"""
from app.models.citation import Citation
from app.models.documents import (
    CorpusManifest,
    DocumentInfo,
    DocumentPage,
    TableAsset,
)
from app.models.execution import ExecutionResult
from app.models.messages import AgentResponse, ChatRequest, Message, Role
from app.models.tools import ToolCall, ToolResult, ToolSpec
from app.models.trace import Span, Trace

__all__ = [
    "Citation",
    "CorpusManifest",
    "DocumentInfo",
    "DocumentPage",
    "TableAsset",
    "ExecutionResult",
    "AgentResponse",
    "ChatRequest",
    "Message",
    "Role",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
    "Span",
    "Trace",
]

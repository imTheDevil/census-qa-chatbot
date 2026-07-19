"""Orchestrator (orchestrator-worker pattern, agents-as-tools).

An engine.Agent whose tools are the two specialists (`research`, `analyze`). It
decomposes the question, delegates, and composes the final cited answer. Owns
conversation memory and does the final citation reconciliation.
"""
from __future__ import annotations

from app.agent.engine import Agent, REFUSAL_PREFIX, reconcile_citations
from app.agent.llm import LLMClient, make_llm
from app.agent.prompts import ORCHESTRATOR_PROMPT
from app.agent.specialists import build_data_agent, build_retrieval_agent
from app.config import get_settings
from app.memory.session import SessionStore
from app.models.messages import AgentResponse, Message
from app.models.tools import ToolResult
from app.models.trace import Trace
from app.tools.base import RunContext, Tool, ToolRegistry


class DelegateTool(Tool):
    """Exposes a specialist agent to the orchestrator as a single tool."""

    parameters = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "A clear, self-contained instruction naming the region "
                "and metric/topic (e.g. 'top 5 districts in Odisha by population').",
            }
        },
        "required": ["task"],
    }

    def __init__(self, name: str, description: str, agent: Agent):
        self.name = name
        self.description = description
        self._agent = agent

    def run(self, ctx: RunContext, task: str) -> ToolResult:
        result = self._agent.run_task(task, ctx)
        return ToolResult(
            tool_call_id="", name=self.name, ok=True,
            content=result.text or "(the specialist returned nothing)",
            citations=result.citations, artifacts=result.artifacts,
        )


class Orchestrator:
    """Top-level entry point: one `run` per user turn."""

    def __init__(self, retrieval: Agent | None = None, data: Agent | None = None,
                 llm: LLMClient | None = None, store: SessionStore | None = None):
        settings = get_settings()
        self._store = store or SessionStore()
        self._retrieval = retrieval or build_retrieval_agent()
        self._data = data or build_data_agent()
        registry = ToolRegistry([
            DelegateTool(
                "research",
                "Delegate a lookup or summary to the retrieval specialist (searches "
                "the document text, reads sections). Returns findings with citations.",
                self._retrieval,
            ),
            DelegateTool(
                "analyze",
                "Delegate a computation, ranking, table, or chart to the data "
                "specialist (queries clean datasets, runs code). Returns results, "
                "any chart/table artifacts, and citations.",
                self._data,
            ),
        ])
        self._agent = Agent(
            name="orchestrator",
            system_prompt=ORCHESTRATOR_PROMPT,
            registry=registry,
            llm=llm or make_llm(settings.model_for("orchestrator")),
            throttle_tools={"research", "analyze"},
            throttle_cap=4,
            throttle_message=(
                "You've delegated enough. Compose the final answer now from what the "
                "specialists returned (keep their citations), or reply 'NOT_FOUND:'."
            ),
        )

    def run(self, session_id: str, user_message: str) -> AgentResponse:
        trace = Trace(session_id=session_id, user_message=user_message)
        ctx = RunContext(
            session_id=session_id,
            workspace=self._store.workspace(session_id),
            trace=trace,
        )
        history = self._store.recent_provider_history(session_id)
        result = self._agent.run_task(user_message, ctx, history=history)

        final_text = result.text
        refused = final_text.strip().startswith(REFUSAL_PREFIX)
        if refused:
            final_text = final_text.strip()[len(REFUSAL_PREFIX):].strip()

        # Persist Q&A only (tool transcript lives in the trace).
        self._store.save_history(
            session_id,
            self._store.load_history(session_id)
            + [Message(role="user", content=user_message),
               Message(role="assistant", content=final_text)],
        )
        trace.finish()
        self._store.save_trace(session_id, trace)

        return AgentResponse(
            session_id=session_id,
            text=final_text,
            citations=[] if refused else reconcile_citations(final_text, result.citations),
            artifacts=result.artifacts,
            refused=refused,
            trace_id=trace.id,
        )

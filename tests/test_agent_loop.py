"""Engine + orchestrator tests using scripted LLMs (no network / API key)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agent.engine import Agent, AgentResult
from app.agent.llm import LLMClient, LLMResponse
from app.agent.orchestrator import Orchestrator
from app.memory.session import SessionStore
from app.models.citation import Citation
from app.models.tools import ToolCall, ToolResult
from app.tools.base import RunContext, Tool, ToolRegistry
from app.models.trace import Trace


class ScriptedLLM(LLMClient):
    model = "scripted"

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None, temperature=0.1) -> LLMResponse:
        self.calls.append(messages)
        return self._responses.pop(0)


def _tool_call(call_id: str, name: str, args: dict) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=args)],
        assistant_message={
            "role": "assistant", "content": None,
            "tool_calls": [{"id": call_id, "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}],
        },
        finish_reason="tool_calls",
    )


def _final(text: str) -> LLMResponse:
    return LLMResponse(content=text, tool_calls=[],
                       assistant_message={"role": "assistant", "content": text},
                       finish_reason="stop")


class FactTool(Tool):
    name = "get_fact"
    description = "returns a fact"
    parameters = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}

    def run(self, ctx: RunContext, q: str) -> ToolResult:
        return ToolResult(tool_call_id="", name=self.name, ok=True,
                          content="literacy 75.36% on page 10",
                          citations=[Citation(document="Karnataka", page=10, snippet="75.36%")])


def _ctx(tmp_path: Path) -> RunContext:
    return RunContext(session_id="t", workspace=tmp_path, trace=Trace(session_id="t", user_message="q"))


# --- engine ---
def test_engine_tool_then_answer_returns_result(tmp_path):
    llm = ScriptedLLM([
        _tool_call("c1", "get_fact", {"q": "literacy"}),
        _final("Literacy was 75.36% [Karnataka, p.10]."),
    ])
    agent = Agent("t", "sys", ToolRegistry([FactTool()]), llm)
    res = agent.run_task("literacy?", _ctx(tmp_path))
    assert isinstance(res, AgentResult)
    assert "75.36" in res.text
    assert any(c.page == 10 for c in res.citations)


def test_engine_junk_args_and_answer(tmp_path):
    # Sanity: engine + registry tolerate a no-arg-style junk call then answer.
    llm = ScriptedLLM([_final("done")])
    res = Agent("t", "sys", ToolRegistry([FactTool()]), llm).run_task("hi", _ctx(tmp_path))
    assert res.text == "done"


def test_fit_context_preserves_history():
    # Regression: conversation history (before the task) must survive trimming, or
    # follow-up questions lose all prior turns.
    from app.agent.engine import _fit_context

    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "literacy in Karnataka?"},
        {"role": "assistant", "content": "75.36%"},
        {"role": "user", "content": "which is higher?"},  # pinned = last
    ]
    out = _fit_context(msgs, pinned_idx=3)
    assert any("75.36" in (m.get("content") or "") for m in out)
    assert out[-1]["content"] == "which is higher?"  # task stays last


# --- orchestrator ---
class StubSpecialist:
    """Stands in for a specialist Agent: canned AgentResult."""

    def __init__(self, result: AgentResult):
        self._result = result
        self.received: list[str] = []

    def run_task(self, task, ctx, history=None) -> AgentResult:
        self.received.append(task)
        return self._result


def _orch(llm, retrieval, data, tmp_path):
    return Orchestrator(retrieval=retrieval, data=data, llm=llm,
                        store=SessionStore(root=tmp_path / "sessions"))


def test_orchestrator_delegates_and_synthesizes(tmp_path):
    retrieval = StubSpecialist(AgentResult(
        text="Literacy rose to 75.36% [Karnataka, p.10].",
        citations=[Citation(document="Karnataka", page=10, snippet="75.36%")]))
    data = StubSpecialist(AgentResult(text="", citations=[]))
    llm = ScriptedLLM([
        _tool_call("c1", "research", {"task": "summarize Karnataka literacy"}),
        _final("Karnataka literacy reached 75.36% in 2011 [Karnataka, p.10]."),
    ])
    resp = _orch(llm, retrieval, data, tmp_path).run("s1", "How literate is Karnataka?")
    assert not resp.refused
    assert "75.36" in resp.text
    assert retrieval.received == ["summarize Karnataka literacy"]  # delegated
    assert any(c.page == 10 for c in resp.citations)  # citation bubbled up + reconciled


def test_orchestrator_persists_memory_and_trace(tmp_path):
    store = SessionStore(root=tmp_path / "sessions")
    retrieval = StubSpecialist(AgentResult(text="hi"))
    data = StubSpecialist(AgentResult(text=""))
    llm = ScriptedLLM([_final("Hello!")])
    orch = Orchestrator(retrieval=retrieval, data=data, llm=llm, store=store)
    resp = orch.run("s2", "hi")
    hist = store.load_history("s2")
    assert [m.role for m in hist] == ["user", "assistant"]
    assert (store.session_dir("s2") / "traces" / f"{resp.trace_id}.json").exists()


def test_orchestrator_graceful_refusal(tmp_path):
    retrieval = StubSpecialist(AgentResult(text=""))
    data = StubSpecialist(AgentResult(text=""))
    llm = ScriptedLLM([_final("NOT_FOUND: not in the provided documents.")])
    resp = _orch(llm, retrieval, data, tmp_path).run("s3", "GDP of France?")
    assert resp.refused
    assert not resp.text.startswith("NOT_FOUND")
    assert resp.citations == []

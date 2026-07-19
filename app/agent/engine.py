"""Reusable ReAct agent engine.

An `Agent` is a role (system prompt + tools + model); `run_task` runs the
think/act/observe loop and returns an `AgentResult`. Stateless, so it powers both
the specialists and the orchestrator. Loop guards (stop conditions, repeated-call
and throttle caps, empty-answer nudge, context trimming) live here.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.agent.llm import LLMClient
from app.config import get_settings
from app.models.citation import Citation
from app.models.tools import ToolResult
from app.models.trace import Trace
from app.tools import ToolRegistry
from app.tools.base import RunContext

# Inline references like [Karnataka, p.10] / 【Karnataka p.9】 (tolerant of brackets/comma).
_INLINE_CITE = re.compile(r"[\[【]([A-Za-z][A-Za-z .]*?),?\s*p\.?\s*(\d+)[\]】]")
REFUSAL_PREFIX = "NOT_FOUND:"
_MAX_TOOL_RETRIES = 3
_MAX_EMPTY_RETRIES = 2
_CONTEXT_BUDGET_CHARS = 16000


@dataclass
class AgentResult:
    text: str
    citations: list[Citation] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)


def _msg_size(m: dict) -> int:
    return len(str(m.get("content") or "")) + len(str(m.get("tool_calls") or ""))


def _fit_context(messages: list[dict], pinned_idx: int, budget: int = _CONTEXT_BUDGET_CHARS) -> list[dict]:
    """Trim to a char budget while ALWAYS keeping the system message and the current
    task. Conversation history (before the task) and current-turn tool results (after)
    are both preserved as far as the budget allows — current-turn results first, then
    as much recent history as fits — so follow-up questions still see prior turns.
    """
    system = messages[0]
    before = messages[1:pinned_idx]          # conversation history (user/assistant)
    pinned = messages[pinned_idx]            # the current task
    after = messages[pinned_idx + 1 :]       # this turn's assistant/tool messages

    groups: list[list[dict]] = []
    for m in after:
        if m.get("role") == "assistant" and groups:
            groups.append([m])
        elif not groups:
            groups.append([m])
        else:
            groups[-1].append(m)

    total = _msg_size(system) + _msg_size(pinned)
    # Current-turn tool results take priority (newest whole groups first).
    kept_after: list[list[dict]] = []
    for g in reversed(groups):
        gsize = sum(_msg_size(m) for m in g)
        if kept_after and total + gsize > budget:
            break
        kept_after.append(g)
        total += gsize
    kept_after.reverse()

    # Then keep as much recent history as still fits (newest first).
    kept_before: list[dict] = []
    for m in reversed(before):
        size = _msg_size(m)
        if total + size > budget:
            break
        kept_before.append(m)
        total += size
    kept_before.reverse()
    while kept_before and kept_before[0].get("role") == "tool":
        kept_before.pop(0)

    result = [system, *kept_before, pinned]
    for g in kept_after:
        result.extend(g)
    return result


def dedupe_citations(cites: list[Citation]) -> list[Citation]:
    seen, out = set(), []
    for c in cites:
        key = (c.document, c.page, c.snippet)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def reconcile_citations(text: str, gathered: list[Citation]) -> list[Citation]:
    """Prefer citations the answer references inline; else return all (deduped)."""
    refs = {(d.strip().lower(), int(p)) for d, p in _INLINE_CITE.findall(text)}
    gathered = dedupe_citations(gathered)
    if not refs:
        return gathered
    matched = [c for c in gathered if (c.document.lower(), c.page) in refs]
    return matched or gathered


class Agent:
    """A role-configurable ReAct agent. Stateless; run_task per task."""

    def __init__(
        self,
        name: str,
        system_prompt: str,
        registry: ToolRegistry,
        llm: LLMClient,
        step_cap: int | None = None,
        throttle_tools: set[str] | None = None,
        throttle_cap: int = 6,
        throttle_message: str | None = None,
    ):
        self.name = name
        self._system = system_prompt
        self._registry = registry
        self._llm = llm
        self._settings = get_settings()
        self._step_cap = step_cap or self._settings.max_agent_steps
        self._throttle_tools = throttle_tools or set()
        self._throttle_cap = throttle_cap
        self._throttle_message = throttle_message or (
            "Enough discovery. Produce your final answer now with [Doc, p.N] "
            "citations, or reply 'NOT_FOUND:' if the documents don't contain it."
        )

    def run_task(self, task: str, ctx: RunContext, history: list[dict] | None = None) -> AgentResult:
        trace = ctx.trace or Trace(session_id=ctx.session_id, user_message=task)
        messages = [{"role": "system", "content": self._system}, *(history or []),
                    {"role": "user", "content": task}]
        pinned_idx = len(messages) - 1

        citations: list[Citation] = []
        artifacts: list[str] = []
        seen_calls: set[str] = set()
        final_text = ""
        tool_retries = empty_retries = throttle_count = 0

        for _ in range(self._step_cap):
            span = trace.start_span("llm", self._llm.model, agent=self.name,
                                    num_messages=len(messages))
            try:
                temperature = min(0.6, self._settings.llm_temperature + 0.25 * tool_retries)
                resp = self._llm.chat(
                    _fit_context(messages, pinned_idx),
                    tools=self._registry.specs(), temperature=temperature,
                )
            except Exception as exc:  # noqa: BLE001
                span.finish(error=str(exc))
                if "tool_use_failed" in str(exc) and tool_retries < _MAX_TOOL_RETRIES:
                    tool_retries += 1
                    messages.append({"role": "user", "content": (
                        "Your previous tool call was rejected: arguments were not valid "
                        "JSON. Call the tool again with a strict JSON object.")})
                    continue
                final_text = f"The model call failed: {exc}"
                break
            span.finish(output={
                "finish_reason": resp.finish_reason,
                "tool_calls": [tc.name for tc in resp.tool_calls],
                "content_preview": (resp.content or "")[:200],
            })
            messages.append(resp.assistant_message)

            if not resp.tool_calls:
                final_text = resp.content or ""
                if not final_text.strip() and empty_retries < _MAX_EMPTY_RETRIES:
                    empty_retries += 1
                    messages.append({"role": "user", "content": (
                        "You returned an empty answer. Either give your final answer "
                        "with [Document, p.N] citations, or reply 'NOT_FOUND:' if the "
                        "documents don't contain it.")})
                    continue
                break

            for tc in resp.tool_calls:
                tspan = trace.start_span("tool", tc.name, agent=self.name, arguments=tc.arguments)
                sig = f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"
                if tc.name in self._throttle_tools:
                    throttle_count += 1
                if sig in seen_calls:
                    result = ToolResult(tool_call_id=tc.id, name=tc.name, ok=True, content=(
                        "You already made this exact call and have its result. Do not "
                        "repeat it — answer now, or take a different action."))
                elif tc.name in self._throttle_tools and throttle_count > self._throttle_cap:
                    result = ToolResult(tool_call_id=tc.id, name=tc.name, ok=True,
                                        content=self._throttle_message)
                else:
                    seen_calls.add(sig)
                    result = self._registry.run(tc.name, ctx, tc.arguments)
                tspan.finish(output={
                    "ok": result.ok, "citations": len(result.citations),
                    "artifacts": result.artifacts, "content_preview": result.content[:300],
                }, error=result.error)
                citations.extend(result.citations)
                artifacts.extend(result.artifacts)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "name": tc.name, "content": result.content})
        else:
            final_text = final_text or (
                "I couldn't finish within the step budget. Please narrow the question.")

        return AgentResult(
            text=final_text,
            citations=dedupe_citations(citations),
            artifacts=list(dict.fromkeys(artifacts)),
        )

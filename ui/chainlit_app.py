"""Chainlit chat UI — a thin client over the FastAPI agent.

Sends messages to POST /chat, renders the answer with citations, shows artifacts
inline, and exposes the trace as collapsible Steps. Set API_URL to point at the API
(default http://localhost:8000).
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid

# Chainlit loads this file directly, so the repo root isn't on sys.path — add it
# so `app` imports resolve when running `chainlit run ui/chainlit_app.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chainlit as cl  # noqa: E402
import httpx  # noqa: E402

from app.memory.session import SessionStore  # noqa: E402

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

# Artifacts live on the same machine as this UI, so serve them by local file path
# (through Chainlit) rather than a URL to the API — no dependency on the API port
# being reachable from the browser.
_store = SessionStore()

# The model sometimes embeds its own markdown image with a bare filename; strip it
# since we render artifacts as real elements below the text.
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


@cl.on_chat_start
async def start() -> None:
    cl.user_session.set("session_id", uuid.uuid4().hex)
    await cl.Message(
        content=(
            "**Census Q&A** — ask about the 2011 PCA Data Highlights for "
            "**Karnataka, Odisha, and Madhya Pradesh**.\n\n"
            "Try: *“Which district in Karnataka had the highest sex ratio?”*, "
            "*“Chart the top 10 districts by population in Odisha.”*, or "
            "*“Summarize the key literacy findings for MP.”*"
        )
    ).send()


def _as_text(value) -> str:
    """Render a span's input/output payload as a readable string (Chainlit Step
    fields are strings, not dicts)."""
    if not value:
        return ""
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _trace_summary(trace: dict) -> str:
    """One-line summary shown on the collapsed parent step."""
    spans = trace.get("spans", [])
    tools = [s["name"] for s in spans if s.get("kind") == "tool"]
    llm = sum(1 for s in spans if s.get("kind") == "llm")
    parts = [f"{llm} LLM call(s)"]
    if tools:
        parts.append("tools: " + ", ".join(dict.fromkeys(tools)))
    return " · ".join(parts)


async def _render_trace(trace: dict | None) -> None:
    """Nest each recorded LLM/tool call as a child Step under the current parent."""
    if not trace:
        return
    for span in trace.get("spans", []):
        agent = span.get("agent", "")
        prefix = f"[{agent}] " if agent else ""
        label = f"{prefix}{span['kind']}: {span['name']}"
        async with cl.Step(name=label, type=span["kind"]) as step:
            step.input = _as_text(span.get("input"))
            output = span.get("output") or {}
            if span.get("error"):
                output = {**output, "error": span["error"]}
            step.output = _as_text(output)


def _artifact_elements(session_id: str, artifacts: list[str]) -> list:
    workspace = _store.workspace(session_id)
    elements = []
    for rel in artifacts:
        path = str(workspace / rel)
        if not os.path.isfile(path):
            continue
        name = rel.split("/")[-1]
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".gif")):
            elements.append(cl.Image(path=path, name=name, display="inline"))
        else:
            elements.append(cl.File(path=path, name=name, display="inline"))
    return elements


def _format_sources(citations: list[dict]) -> str:
    lines = []
    for c in citations:
        loc = c["document"] + (f", p.{c['page']}" if c.get("page") else "")
        snippet = (c.get("snippet") or "").strip().replace("\n", " ")
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        lines.append(f"- **[{loc}]** “{snippet}”")
    return "\n".join(lines)


@cl.on_message
async def on_message(message: cl.Message) -> None:
    session_id = cl.user_session.get("session_id")

    # A single parent step: shows a spinner while the agent runs (loading state),
    # then collapses into one dropdown holding every tool/LLM sub-step — kept above
    # the final answer, like a "thinking" panel.
    data: dict | None = None
    # One parent step: spins while the agent runs, then collapses into a dropdown
    # holding every tool/LLM sub-step. Named so the "Using…/Used…" prefix Chainlit
    # adds reads naturally (not the confusing "Using Analyzing").
    async with cl.Step(name="reasoning & tool calls", type="run") as parent:
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{API_URL}/chat",
                    json={"session_id": session_id, "message": message.content},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            parent.output = f"Error: {exc}"
            await cl.Message(content=f"⚠️ Could not reach the agent API: {exc}").send()
            return

        await _render_trace(data.get("trace"))
        if data.get("trace"):
            parent.output = _trace_summary(data["trace"])

    answer = data["answer"]
    # Drop any inline image markdown the model wrote (bare filenames that don't
    # resolve); the chart is rendered as a real element instead.
    body = _MD_IMAGE.sub("", answer["text"] or "").strip() or "*(no answer)*"
    if answer.get("refused"):
        body = "🚫 " + body

    # Response order: answer text, then artifacts (chart), then Sources last.
    await cl.Message(
        content=body,
        elements=_artifact_elements(session_id, answer.get("artifacts", [])),
    ).send()

    citations = answer.get("citations", [])
    if not answer.get("refused") and citations:
        async with cl.Step(name=f"Sources ({len(citations)})", type="tool") as src:
            src.output = _format_sources(citations)

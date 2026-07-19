"""LLM provider abstraction.

`OpenAICompatibleClient` targets any OpenAI-compatible chat-completions endpoint with
tool calling (NVIDIA NIM by default), so switching providers is a config change.
`LLMResponse` normalizes the assistant text, parsed tool calls, and raw message.
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.models.tools import ToolCall

# Back off and retry when the provider rate-limits us.
_MAX_RATE_RETRIES = 4
_RETRY_AFTER_RE = re.compile(r"(?:try again in|retry.{0,10}?)([\d.]+)s", re.IGNORECASE)


def _clean_tool_name(name: str) -> str:
    """Strip gpt-oss 'harmony' channel tokens that leak into tool-call names on
    some endpoints, e.g. 'search_documents<|channel|>commentary' -> 'search_documents'.
    """
    if not name:
        return name
    for sep in ("<|", "<", "|"):
        if sep in name:
            name = name.split(sep)[0]
    return name.strip()


# gpt-oss sometimes leaks its harmony/tool-call syntax into the message content.
_HARMONY_TOKEN = re.compile(r"<\|[^|>]*\|>")
_HARMONY_TRAIL = re.compile(r"(【analysis|to=functions\.|assistant(final|analysis)).*", re.DOTALL)
# The orchestrator sometimes brackets a tool/agent name as if it were a source.
_TOOL_CITE = re.compile(r"[\[【]\s*(research|analyze|data|retrieval|tool)\s*[\]】]", re.IGNORECASE)


def _clean_content(text: str | None) -> str | None:
    """Remove leaked harmony/tool-call tokens and tool-name pseudo-citations."""
    if not text:
        return text
    text = _HARMONY_TOKEN.sub("", text)
    text = _HARMONY_TRAIL.sub("", text)  # drop trailing tool-call leakage
    text = _TOOL_CITE.sub("", text)      # drop [research]/【analyze】 pseudo-citations
    return text.strip()


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]
    assistant_message: dict[str, Any]  # provider-format, appended to history verbatim
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient(ABC):
    model: str

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
    ) -> LLMResponse:
        ...


class OpenAICompatibleClient(LLMClient):
    """Client for any OpenAI-compatible endpoint (NVIDIA NIM, OpenAI, vLLM, ...)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ):
        from openai import OpenAI  # imported lazily so tests run without the dep

        settings = get_settings()
        key = api_key or settings.llm_api_key
        if not key:
            raise RuntimeError(
                "LLM_API_KEY is not set. Add it to .env (see .env.example)."
            )
        self._client = OpenAI(api_key=key, base_url=base_url or settings.llm_base_url)
        self.model = model or settings.llm_model
        self._reasoning_effort = (
            reasoning_effort if reasoning_effort is not None else settings.reasoning_effort
        )

    def chat(self, messages, tools=None, temperature=0.1) -> LLMResponse:
        from openai import RateLimitError

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if "gpt-oss" in self.model and self._reasoning_effort:
            # gpt-oss reasoning hint; via extra_body for SDK-version independence.
            kwargs["extra_body"] = {"reasoning_effort": self._reasoning_effort}

        resp = None
        for attempt in range(_MAX_RATE_RETRIES):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                break
            except RateLimitError as exc:
                if attempt == _MAX_RATE_RETRIES - 1:
                    raise
                m = _RETRY_AFTER_RE.search(str(exc))
                wait = float(m.group(1)) + 0.5 if m else 15.0
                print(f"[llm] rate limited; retrying in {wait:.1f}s")
                time.sleep(min(wait, 60))

        choice = resp.choices[0]
        msg = choice.message

        tool_calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCall(id=tc.id, name=_clean_tool_name(tc.function.name), arguments=args)
            )

        # Resend only the fields we need; drop any large provider-private fields
        # (e.g. reasoning) that would otherwise balloon the context each turn.
        dumped = msg.model_dump(exclude_none=True)
        assistant_message = {
            k: dumped[k] for k in ("role", "content", "tool_calls") if k in dumped
        }
        if assistant_message.get("content"):
            assistant_message["content"] = _clean_content(assistant_message["content"])
        # Clean harmony-token leakage in resent tool-call names too.
        for tc in assistant_message.get("tool_calls", []):
            fn = tc.get("function", {})
            if "name" in fn:
                fn["name"] = _clean_tool_name(fn["name"])

        return LLMResponse(
            content=_clean_content(msg.content),
            tool_calls=tool_calls,
            assistant_message=assistant_message,
            usage=resp.usage.model_dump() if resp.usage else None,
            finish_reason=choice.finish_reason,
        )


def get_llm() -> LLMClient:
    return OpenAICompatibleClient()


def make_llm(model: str | None = None, reasoning_effort: str | None = None) -> LLMClient:
    """Construct a client with a specific model/effort (for per-agent tuning)."""
    return OpenAICompatibleClient(model=model, reasoning_effort=reasoning_effort)

"""Filesystem-backed session memory.

Each session owns a dir workspace/sessions/{id}/ holding history.json (conversation),
artifacts/ (files from execute_python), and traces/ (per-turn records).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import get_settings
from app.models.messages import Message
from app.models.trace import Trace

_SAFE_ID = re.compile(r"[^a-zA-Z0-9_-]")


class SessionStore:
    def __init__(self, root: Path | None = None):
        self._root = root or get_settings().workspace_path

    def _sid(self, session_id: str) -> str:
        return _SAFE_ID.sub("_", session_id)[:64] or "default"

    def session_dir(self, session_id: str) -> Path:
        d = self._root / self._sid(session_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def workspace(self, session_id: str) -> Path:
        """The per-session working dir handed to tools (artifacts live under it)."""
        return self.session_dir(session_id)

    # --- conversation history ---
    def _history_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "history.json"

    def load_history(self, session_id: str) -> list[Message]:
        path = self._history_path(session_id)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [Message.model_validate(m) for m in raw]

    def save_history(self, session_id: str, messages: list[Message]) -> None:
        self._history_path(session_id).write_text(
            json.dumps([m.model_dump(exclude_none=True) for m in messages], indent=2),
            encoding="utf-8",
        )

    def recent_provider_history(
        self, session_id: str, max_messages: int = 20
    ) -> list[dict]:
        """Recent history in provider-message format, trimmed to a message budget.

        Trims from the front but never starts on an orphan 'tool' message (which
        must follow its assistant tool_calls message), keeping the slice valid.
        """
        msgs = self.load_history(session_id)
        window = msgs[-max_messages:]
        while window and window[0].role == "tool":
            window = window[1:]
        return [m.to_provider() for m in window]

    # --- traces ---
    def save_trace(self, session_id: str, trace: Trace) -> None:
        tdir = self.session_dir(session_id) / "traces"
        tdir.mkdir(exist_ok=True)
        (tdir / f"{trace.id}.json").write_text(
            trace.model_dump_json(indent=2), encoding="utf-8"
        )

    def load_trace(self, session_id: str, trace_id: str) -> Trace | None:
        path = self.session_dir(session_id) / "traces" / f"{_SAFE_ID.sub('_', trace_id)}.json"
        if not path.exists():
            return None
        return Trace.model_validate_json(path.read_text(encoding="utf-8"))

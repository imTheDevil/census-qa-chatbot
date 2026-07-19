"""Result contract for the code-execution tool.

The agent writes Python and runs it in a sandboxed subprocess. This captures
everything the agent (and a human reviewer) needs to reason about the run:
stdout, stderr, produced artifact files, and a clean error field when it fails.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExecutionResult(BaseModel):
    """Outcome of one `execute_python` call."""

    ok: bool = Field(description="True if the code ran without raising.")
    stdout: str = Field(default="", description="Captured standard output.")
    stderr: str = Field(default="", description="Captured standard error.")
    artifacts: list[str] = Field(
        default_factory=list,
        description="Paths (relative to the session workspace) of files the code produced.",
    )
    error: str | None = Field(
        default=None,
        description="Short error summary (exception type + message, or 'timeout').",
    )
    duration_ms: int = Field(default=0, description="Wall-clock execution time.")

    def to_observation(self, max_len: int = 4000) -> str:
        """Compact text fed back to the LLM as the tool observation."""
        parts: list[str] = []
        if self.stdout:
            parts.append(f"STDOUT:\n{self.stdout}")
        if self.stderr:
            parts.append(f"STDERR:\n{self.stderr}")
        if self.error:
            parts.append(f"ERROR: {self.error}")
        if self.artifacts:
            parts.append("ARTIFACTS: " + ", ".join(self.artifacts))
        if not parts:
            parts.append("(no output)")
        text = "\n\n".join(parts)
        return text if len(text) <= max_len else text[: max_len - 3] + "..."

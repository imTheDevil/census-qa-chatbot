"""Central configuration, loaded from environment / .env.

Every path and provider setting flows through here so components never hardcode
locations. Uses pydantic-settings so config is typed and validated at startup.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (app/config.py -> app -> root).
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM provider (OpenAI-compatible; NVIDIA NIM by default) ---
    # Any OpenAI-compatible endpoint works — set LLM_BASE_URL + LLM_MODEL to swap.
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1", alias="LLM_BASE_URL"
    )
    # gpt-oss-20b: fast (~sub-second/call on NVIDIA NIM) + reliable tool calling.
    # The larger 120b is more capable but much slower; llama models are heavily
    # queued on NVIDIA's public tier (tens of seconds/call).
    llm_model: str = Field(default="openai/gpt-oss-20b", alias="LLM_MODEL")

    # Per-agent model overrides (empty -> use llm_model). Lets you run e.g. a
    # lighter orchestrator without touching code.
    orchestrator_model: str = Field(default="", alias="ORCHESTRATOR_MODEL")
    retrieval_model: str = Field(default="", alias="RETRIEVAL_MODEL")
    data_model: str = Field(default="", alias="DATA_MODEL")

    def model_for(self, role: str) -> str:
        override = {
            "orchestrator": self.orchestrator_model,
            "retrieval": self.retrieval_model,
            "data": self.data_model,
        }.get(role, "")
        return override or self.llm_model

    # --- Agent loop ---
    max_agent_steps: int = Field(default=16, alias="MAX_AGENT_STEPS")
    llm_temperature: float = Field(default=0.1, alias="LLM_TEMPERATURE")
    # gpt-oss reasoning hint. low keeps latency down; medium plans better but on the
    # 120b it explodes reasoning tokens (minutes/turn). Ignored for non-gpt-oss models.
    reasoning_effort: str = Field(default="low", alias="REASONING_EFFORT")

    # --- Code execution sandbox ---
    code_exec_timeout_s: int = Field(default=20, alias="CODE_EXEC_TIMEOUT_S")

    # --- Paths (relative to repo root unless absolute) ---
    data_markdown_dir: str = Field(default="data/markdown", alias="DATA_MARKDOWN_DIR")
    data_processed_dir: str = Field(
        default="data/processed", alias="DATA_PROCESSED_DIR"
    )
    workspace_dir: str = Field(default="workspace/sessions", alias="WORKSPACE_DIR")
    recipes_dir: str = Field(default="recipes", alias="RECIPES_DIR")

    def _resolve(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else ROOT_DIR / p

    @property
    def markdown_path(self) -> Path:
        return self._resolve(self.data_markdown_dir)

    @property
    def processed_path(self) -> Path:
        return self._resolve(self.data_processed_dir)

    @property
    def workspace_path(self) -> Path:
        return self._resolve(self.workspace_dir)

    @property
    def recipes_path(self) -> Path:
        return self._resolve(self.recipes_dir)


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so all components share one config instance."""
    return Settings()

"""FastAPI agent API.

Endpoints: POST /chat (returns the answer + full trace), GET /artifacts/... (serve a
produced chart/csv), GET /health (corpus summary).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.agent.orchestrator import Orchestrator
from app.config import get_settings
from app.ingestion.build_corpus import build
from app.memory.session import SessionStore
from app.models.messages import AgentResponse, ChatRequest
from app.models.trace import Trace

_settings = get_settings()
_store = SessionStore()
_agent: Orchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the corpus index on first boot if it isn't there yet.
    if not (_settings.processed_path / "manifest.json").exists():
        print("No corpus index found — running ingestion...")
        build(_settings.markdown_path, _settings.processed_path)
    yield


app = FastAPI(title="Census Q&A Chatbot", version="0.1.0", lifespan=lifespan)


class ChatResponse(BaseModel):
    answer: AgentResponse
    trace: Trace | None = None


def get_agent() -> Orchestrator:
    """Lazily construct the orchestrator (so import doesn't require an API key)."""
    global _agent
    if _agent is None:
        _agent = Orchestrator(store=_store)
    return _agent


@app.get("/health")
def health() -> dict:
    from app.ingestion.corpus_store import get_corpus_store

    try:
        docs = get_corpus_store().manifest.documents
        corpus = {d.label: d.num_pages for d in docs}
    except Exception as exc:  # noqa: BLE001
        corpus = {"error": str(exc)}
    return {"status": "ok", "model": _settings.llm_model, "corpus": corpus}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, agent: Orchestrator = Depends(get_agent)) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Empty message.")
    answer = agent.run(req.session_id, req.message)
    trace = _store.load_trace(req.session_id, answer.trace_id)
    return ChatResponse(answer=answer, trace=trace)


@app.get("/artifacts/{session_id}/{artifact_path:path}")
def get_artifact(session_id: str, artifact_path: str) -> FileResponse:
    workspace = _store.workspace(session_id).resolve()
    target = (workspace / artifact_path).resolve()
    # Prevent path traversal outside the session workspace.
    if not str(target).startswith(str(workspace)) or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(target)

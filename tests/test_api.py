"""API tests using FastAPI's TestClient and a fake agent (no LLM key needed)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app, get_agent
from app.models.messages import AgentResponse


class FakeAgent:
    def run(self, session_id: str, message: str) -> AgentResponse:
        return AgentResponse(
            session_id=session_id,
            text=f"echo: {message}",
            citations=[],
            artifacts=[],
            refused=False,
            trace_id="trace_test",
        )


def _client() -> TestClient:
    app.dependency_overrides[get_agent] = lambda: FakeAgent()
    return TestClient(app)


def test_chat_returns_answer():
    client = _client()
    r = client.post("/chat", json={"session_id": "s1", "message": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"]["text"] == "echo: hello"
    app.dependency_overrides.clear()


def test_empty_message_rejected():
    client = _client()
    r = client.post("/chat", json={"session_id": "s1", "message": "   "})
    assert r.status_code == 400
    app.dependency_overrides.clear()


def test_artifact_traversal_blocked():
    client = _client()
    r = client.get("/artifacts/s1/../../../../etc/passwd")
    assert r.status_code == 404
    app.dependency_overrides.clear()

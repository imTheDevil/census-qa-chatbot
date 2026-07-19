"""Multi-agent orchestration: a coordinating orchestrator + two specialists.

Orchestrator (owns memory) delegates to a Retrieval specialist (text lane) and a
Data specialist (data lane), all built on one reusable ReAct engine.
"""
from app.agent.engine import Agent, AgentResult
from app.agent.orchestrator import Orchestrator

__all__ = ["Agent", "AgentResult", "Orchestrator"]

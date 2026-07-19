"""Shared pytest fixtures."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.tools.base import RunContext


@pytest.fixture
def run_ctx():
    """A RunContext with a throwaway session workspace."""
    with tempfile.TemporaryDirectory() as tmp:
        yield RunContext(session_id="test", workspace=Path(tmp))

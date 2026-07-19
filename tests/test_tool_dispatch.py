"""Tool dispatch / argument-sanitization tests.

gpt-oss sometimes calls a tool with junk args (e.g. {"": ""} for a no-arg tool)
or unknown keys. The registry should sanitize these instead of hard-failing, and
give an actionable message only when a genuinely required arg is missing.
"""
from __future__ import annotations

from app.tools.base import RunContext, Tool, ToolRegistry


class NoArgTool(Tool):
    name = "noarg"
    description = "takes nothing"
    parameters = {"type": "object", "properties": {}}

    def run(self, ctx: RunContext) -> "object":
        return self.ok("ran")


class OneArgTool(Tool):
    name = "onearg"
    description = "needs x"
    parameters = {
        "type": "object",
        "properties": {"x": {"type": "string", "description": "the x value"}},
        "required": ["x"],
    }

    def run(self, ctx: RunContext, x: str):
        return self.ok(f"got {x}")


def _reg():
    return ToolRegistry([NoArgTool(), OneArgTool()])


def _ctx(tmp_path):
    return RunContext(session_id="t", workspace=tmp_path)


def test_junk_args_dropped_for_noarg_tool(tmp_path):
    # The exact gpt-oss failure mode: {"": ""} to a no-arg tool.
    res = _reg().run("noarg", _ctx(tmp_path), {"": ""})
    assert res.ok and res.content == "ran"


def test_unknown_keys_dropped(tmp_path):
    res = _reg().run("onearg", _ctx(tmp_path), {"x": "hi", "bogus": 1})
    assert res.ok and "got hi" in res.content


def test_missing_required_arg_gives_actionable_message(tmp_path):
    res = _reg().run("onearg", _ctx(tmp_path), {})
    assert not res.ok
    assert "missing required" in res.content.lower()
    assert "the x value" in res.content  # includes the param description


def test_empty_string_required_treated_as_missing(tmp_path):
    res = _reg().run("onearg", _ctx(tmp_path), {"x": ""})
    assert not res.ok and res.error == "missing_arguments"

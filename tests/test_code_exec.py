"""Code execution tool tests — stdout/stderr capture, errors, timeouts, artifacts."""
from __future__ import annotations

from app.tools.code_exec import ExecutePythonTool


def test_captures_stdout(run_ctx):
    tool = ExecutePythonTool()
    res = tool.run(run_ctx, code="print(6 * 7)")
    assert res.ok
    assert "42" in res.content


def test_handles_exception_cleanly(run_ctx):
    tool = ExecutePythonTool()
    res = tool.run(run_ctx, code="raise ValueError('boom')")
    assert not res.ok
    assert "ValueError" in res.content or "boom" in res.content
    # A crashing snippet must not raise out of the tool.


def test_timeout_is_reported(run_ctx):
    tool = ExecutePythonTool(timeout_s=1)
    res = tool.run(run_ctx, code="while True:\n    pass")
    assert not res.ok
    assert "timeout" in (res.error or "").lower()


def test_artifact_detection(run_ctx):
    tool = ExecutePythonTool()
    code = "with open(save_path('out.txt'), 'w') as f:\n    f.write('hi')"
    res = tool.run(run_ctx, code=code)
    assert res.ok
    assert any("out.txt" in a for a in res.artifacts)


def test_matplotlib_chart_artifact(run_ctx):
    tool = ExecutePythonTool()
    code = (
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1,2,3],[3,1,2])\n"
        "plt.savefig(save_path('chart.png'))\n"
        "print('done')"
    )
    res = tool.run(run_ctx, code=code)
    assert res.ok
    assert any(a.endswith("chart.png") for a in res.artifacts)


def test_forgotten_savefig_is_auto_saved(run_ctx):
    # The model builds a figure but never calls savefig — it must still be captured.
    tool = ExecutePythonTool()
    code = "import matplotlib.pyplot as plt\nplt.bar(['a','b'],[3,5])\nplt.title('x')"
    res = tool.run(run_ctx, code=code)
    assert res.ok
    assert any(a.endswith(".png") for a in res.artifacts)


def test_relative_savefig_redirected_to_artifacts(run_ctx):
    # A bare filename must land in the artifacts dir, not the repo root/cwd.
    tool = ExecutePythonTool()
    code = "import matplotlib.pyplot as plt\nplt.plot([1,2])\nplt.savefig('bare.png')"
    res = tool.run(run_ctx, code=code)
    assert res.ok
    assert res.artifacts == ["artifacts/bare.png"]

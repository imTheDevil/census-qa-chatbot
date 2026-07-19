"""Code execution tool: run model-written Python in a subprocess.

Runs with cwd at the repo root (so csv paths from list_tables work), a headless
matplotlib + save_path() helper, a timeout and POSIX rlimits, and captures
stdout/stderr + any produced artifact files. Not a true security sandbox (see
DESIGN.md) — adequate for running data-analysis code.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from app.config import ROOT_DIR, get_settings
from app.models.execution import ExecutionResult
from app.models.tools import ToolResult
from app.tools.base import RunContext, Tool

_ARTIFACT_EXTS = (".png", ".jpg", ".jpeg", ".svg", ".gif", ".pdf", ".csv", ".html")

_PREAMBLE = """\
import os, sys
import matplotlib
matplotlib.use("Agg")  # headless backend
import matplotlib.pyplot as _plt
import matplotlib.figure as _mfig
ARTIFACTS_DIR = os.environ["ARTIFACTS_DIR"]
os.makedirs(ARTIFACTS_DIR, exist_ok=True)
def save_path(filename):
    \"\"\"Return an absolute path inside the session artifacts dir.\"\"\"
    return os.path.join(ARTIFACTS_DIR, os.path.basename(filename))
# Redirect any savefig with a bare/relative name into the artifacts dir, and count
# saves so we can auto-save a forgotten figure afterward.
_saved = {"n": 0}
def _redirect(fname):
    if isinstance(fname, str) and not os.path.isabs(fname):
        return os.path.join(ARTIFACTS_DIR, os.path.basename(fname))
    return fname
_orig_pltsave = _plt.savefig
def _pltsave(fname, *a, **k):
    _saved["n"] += 1
    return _orig_pltsave(_redirect(fname), *a, **k)
_plt.savefig = _pltsave
_orig_figsave = _mfig.Figure.savefig
def _figsave(self, fname, *a, **k):
    _saved["n"] += 1
    return _orig_figsave(self, _redirect(fname), *a, **k)
_mfig.Figure.savefig = _figsave
# ---- agent code below ----
"""

_POSTAMBLE = """
# Safety net: if the code made figures but never saved one, save them as artifacts.
try:
    if _saved["n"] == 0 and _plt.get_fignums():
        for _i, _num in enumerate(_plt.get_fignums()):
            _p = os.path.join(ARTIFACTS_DIR, "chart.png" if _i == 0 else f"chart_{_i+1}.png")
            _plt.figure(_num).savefig(_p, dpi=120, bbox_inches="tight")
            print("[auto-saved figure]", os.path.basename(_p))
except Exception as _e:
    print("[auto-save failed]", _e)
"""


def _apply_rlimits(cpu_seconds: int) -> None:
    """preexec hook: cap CPU, address space and file size (POSIX only)."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        gb = 2 * 1024 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (gb, gb))
        fsize = 50 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
    except Exception:  # noqa: BLE001 - best effort; not all platforms support this
        pass


class ExecutePythonTool(Tool):
    name = "execute_python"
    description = (
        "Execute Python to compute over the data or build an artifact. Use pandas to "
        "read CSVs from list_tables (paths are relative to the repo root). print() any "
        "result you need to see. To produce a chart/file, save it with "
        "save_path('name.png') — files saved there are shown to the user as artifacts. "
        "matplotlib is preconfigured (headless). stdout, stderr and errors are returned."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "REQUIRED. The complete Python script to run, as a single string "
                    "(e.g. \"import pandas as pd\\ndf = pd.read_csv(...)\\nprint(...)\"). "
                    "Never call this tool without the code argument."
                ),
            }
        },
        "required": ["code"],
    }

    def __init__(self, timeout_s: int | None = None):
        self._timeout = timeout_s or get_settings().code_exec_timeout_s

    def run(self, ctx: RunContext, code: str) -> ToolResult:
        artifacts_dir = ctx.workspace / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        before = self._snapshot(artifacts_dir)
        root_before = self._snapshot(ROOT_DIR)  # catch strays saved to cwd

        script = _PREAMBLE + "\n" + (code or "") + "\n" + _POSTAMBLE
        env = {**os.environ, "ARTIFACTS_DIR": str(artifacts_dir), "MPLBACKEND": "Agg"}

        start = time.time()
        result = self._exec(script, env)
        result.duration_ms = int((time.time() - start) * 1000)

        # New/changed files in the artifacts dir become artifacts.
        after = self._snapshot(artifacts_dir)
        new_files = [name for name, mtime in after.items() if before.get(name) != mtime]

        # Safety net: if the model saved to the repo root (cwd) instead of using
        # save_path(), move those stray artifact files into the session dir.
        root_after = self._snapshot(ROOT_DIR)
        for name, mtime in root_after.items():
            if root_before.get(name) == mtime or not name.lower().endswith(_ARTIFACT_EXTS):
                continue
            src = ROOT_DIR / name
            dst = artifacts_dir / name
            try:
                src.replace(dst)
                new_files.append(name)
            except OSError:
                pass

        result.artifacts = sorted(f"artifacts/{n}" for n in set(new_files))

        return ToolResult(
            tool_call_id="", name=self.name, ok=result.ok,
            content=result.to_observation(), artifacts=result.artifacts,
            error=result.error,
        )

    def _exec(self, script: str, env: dict) -> ExecutionResult:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", script],
                cwd=str(ROOT_DIR),
                env=env,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                preexec_fn=lambda: _apply_rlimits(self._timeout + 5)
                if os.name == "posix" else None,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                ok=False,
                stdout=(exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
                stderr="",
                error=f"timeout after {self._timeout}s",
            )
        error = None
        if proc.returncode != 0:
            tail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else "non-zero exit"
            error = tail
        return ExecutionResult(
            ok=proc.returncode == 0, stdout=proc.stdout, stderr=proc.stderr, error=error
        )

    @staticmethod
    def _snapshot(directory: Path) -> dict[str, float]:
        return {p.name: p.stat().st_mtime for p in directory.iterdir() if p.is_file()}

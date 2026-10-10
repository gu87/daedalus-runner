#!/usr/bin/env python3
"""Automatic verification for delegated subagent tasks.

The daemon marks finished tasks ``waiting_for_verification``; this module
lets the host (Dafu) verify common task shapes automatically instead of
eyeballing every result:

1. Explicit ``TaskSpec.verify_command`` -> run it, exit 0 means pass.
2. Goal mentions tests (pytest / 测试 / test) -> run pytest on detected paths.
3. Goal involves writing files -> check the files exist and are non-empty.
4. Generic fallback -> result.status == "done" and non-empty output.

Verification runs locally via subprocess (it is the host's job, not the
subagent's), always with a timeout.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from tools.delegate_runtime.backend import SubagentResult, TaskSpec

#: Default timeout (seconds) for any verification command.
DEFAULT_VERIFY_TIMEOUT = 60.0

#: Default work dir for relative paths (mirrors the daemon default).
DEFAULT_WORK_DIR = "/home/hatch"

#: Goal keywords that select the pytest strategy.
_PYTEST_KEYWORDS = ("pytest", "单元测试", "测试", "test_")

#: Goal keywords that signal file-writing intent.
_WRITE_KEYWORDS = ("保存到", "保存", "写入", "写到", "生成", "创建", "write", "save")

#: Matches file-like tokens with common extensions inside a goal string.
_FILE_RE = re.compile(r"[a-zA-Z0-9_.\-/]+\.(?:py|md|txt|yaml|yml|json|sh|rs|toml|cfg|ini)\b")


@dataclass
class VerifyResult:
    passed: bool
    details: str
    command_run: str = ""


def _run_command(command: List[str] | str, *, cwd: str, timeout: float) -> tuple[int, str]:
    """Run *command*, return (returncode, combined_output). -1 on timeout."""
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            shell=isinstance(command, str),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()[-2000:]
    except subprocess.TimeoutExpired:
        return -1, f"command timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001 - surface as verification failure
        return -1, f"failed to run command: {exc}"


def _extract_file_paths(goal: str) -> List[str]:
    seen: List[str] = []
    for m in _FILE_RE.finditer(goal):
        p = m.group(0).strip("./")
        if p and p not in seen:
            seen.append(p)
    return seen


def _strategy_pytest(spec: TaskSpec, *, cwd: str, timeout: float) -> VerifyResult:
    paths = _extract_file_paths(spec.goal)
    if paths:
        cmd: List[str] | str = ["python3", "-m", "pytest", *paths, "-q"]
        cmd_str = " ".join(cmd)
    else:
        # No concrete path in the goal: run the repo's test suite root.
        cmd = ["python3", "-m", "pytest", "-q"]
        cmd_str = " ".join(cmd) + "  (no test path found in goal, ran suite root)"
    rc, out = _run_command(cmd, cwd=cwd, timeout=timeout)
    passed = rc == 0
    return VerifyResult(
        passed=passed,
        details=("pytest passed" if passed else f"pytest failed (exit {rc})") + f": {out[-500:]}",
        command_run=cmd_str,
    )


def _strategy_files_exist(spec: TaskSpec, *, cwd: str) -> VerifyResult:
    paths = _extract_file_paths(spec.goal)
    if not paths:
        return VerifyResult(
            passed=False,
            details="file-write task but no file paths found in goal",
        )
    missing = [p for p in paths if not os.path.isfile(os.path.join(cwd, p))]
    empty = [
        p
        for p in paths
        if os.path.isfile(os.path.join(cwd, p))
        and os.path.getsize(os.path.join(cwd, p)) == 0
    ]
    if missing or empty:
        return VerifyResult(
            passed=False,
            details=f"missing: {missing}; empty: {empty}",
        )
    return VerifyResult(passed=True, details=f"{len(paths)} file(s) exist and non-empty: {paths}")


def _strategy_generic(result: SubagentResult) -> VerifyResult:
    if result.status != "done":
        return VerifyResult(passed=False, details=f"task status is {result.status!r}, not 'done'")
    if not (result.output or "").strip():
        return VerifyResult(passed=False, details="task done but output is empty")
    return VerifyResult(passed=True, details="status done and output non-empty")


def auto_verify(
    spec: TaskSpec,
    result: SubagentResult,
    *,
    work_dir: str = DEFAULT_WORK_DIR,
    timeout: float = DEFAULT_VERIFY_TIMEOUT,
) -> VerifyResult:
    """Verify a finished subagent task, picking a strategy automatically.

    Priority: explicit ``spec.verify_command`` > pytest keywords in goal >
    file-write keywords in goal > generic status/output check.
    """
    # 0. Task did not finish: nothing else to check.
    if result.status != "done":
        return VerifyResult(passed=False, details=f"task status is {result.status!r}, not 'done'")

    # 1. Explicit command wins.
    verify_command: Optional[str] = getattr(spec, "verify_command", None)
    if verify_command:
        rc, out = _run_command(verify_command, cwd=work_dir, timeout=timeout)
        passed = rc == 0
        return VerifyResult(
            passed=passed,
            details=("verify_command passed" if passed else f"verify_command failed (exit {rc})")
            + f": {out[-500:]}",
            command_run=verify_command,
        )

    goal = spec.goal or ""
    lowered = goal.lower()

    # 2. Pytest strategy.
    if any(k in lowered for k in _PYTEST_KEYWORDS):
        return _strategy_pytest(spec, cwd=work_dir, timeout=timeout)

    # 3. File-existence strategy.
    if any(k in goal for k in _WRITE_KEYWORDS):
        return _strategy_files_exist(spec, cwd=work_dir)

    # 4. Generic fallback.
    return _strategy_generic(result)

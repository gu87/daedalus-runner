#!/usr/bin/env python3
"""Unit tests for tools.delegate_runtime.verify.auto_verify.

All subprocess invocations are mocked; no real commands run.
"""

from unittest.mock import MagicMock, patch

import pytest

from tools.delegate_runtime.backend import SubagentResult, TaskSpec
from tools.delegate_runtime.verify import VerifyResult, auto_verify


def _spec(goal, **kw):
    return TaskSpec(agent_id="code-worker", goal=goal, **kw)


def _result(status="done", output="some output"):
    return SubagentResult(subagent_id="run-1", status=status, output=output)


def _completed_process(returncode=0, stdout="ok", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ── explicit verify_command ──────────────────────────────────────────────

@patch("tools.delegate_runtime.verify.subprocess.run")
def test_explicit_command_exit_zero_passes(mock_run):
    mock_run.return_value = _completed_process(returncode=0, stdout="3 passed")
    spec = _spec("do anything", verify_command="cd /tmp && pytest -q")
    vr = auto_verify(spec, _result())
    assert isinstance(vr, VerifyResult)
    assert vr.passed is True
    assert vr.command_run == "cd /tmp && pytest -q"
    assert "passed" in vr.details


@patch("tools.delegate_runtime.verify.subprocess.run")
def test_explicit_command_nonzero_fails(mock_run):
    mock_run.return_value = _completed_process(returncode=1, stdout="1 failed")
    spec = _spec("do anything", verify_command="cd /tmp && pytest -q")
    vr = auto_verify(spec, _result())
    assert vr.passed is False
    assert "exit 1" in vr.details


@patch("tools.delegate_runtime.verify.subprocess.run")
def test_explicit_command_beats_pytest_keywords(mock_run):
    # Goal mentions pytest, but explicit command wins.
    mock_run.return_value = _completed_process(returncode=0)
    spec = _spec("写 pytest 测试", verify_command="echo hello")
    vr = auto_verify(spec, _result())
    assert vr.passed is True
    assert vr.command_run == "echo hello"
    mock_run.assert_called_once()


def test_non_done_status_short_circuits_before_command():
    spec = _spec("do anything", verify_command="echo hi")
    vr = auto_verify(spec, _result(status="error"))
    assert vr.passed is False
    assert "error" in vr.details
    assert vr.command_run == ""


# ── pytest strategy ──────────────────────────────────────────────────────

@patch("tools.delegate_runtime.verify.subprocess.run")
def test_pytest_keyword_runs_pytest_on_detected_path(mock_run):
    mock_run.return_value = _completed_process(returncode=0, stdout="5 passed")
    spec = _spec("给 foo 写 pytest 单元测试，保存到 tests/test_foo.py")
    vr = auto_verify(spec, _result())
    assert vr.passed is True
    assert "pytest" in vr.command_run
    assert "tests/test_foo.py" in vr.command_run
    # Called with a list (no shell) for auto-generated commands.
    assert isinstance(mock_run.call_args[0][0], list)


@patch("tools.delegate_runtime.verify.subprocess.run")
def test_pytest_failure_fails_verification(mock_run):
    mock_run.return_value = _completed_process(returncode=2, stdout="2 failed")
    spec = _spec("跑 pytest 看看")
    vr = auto_verify(spec, _result())
    assert vr.passed is False
    assert "exit 2" in vr.details


@patch("tools.delegate_runtime.verify.subprocess.run")
def test_chinese_test_keyword_triggers_pytest(mock_run):
    mock_run.return_value = _completed_process(returncode=0)
    spec = _spec("补一下单元测试")
    vr = auto_verify(spec, _result())
    assert "pytest" in vr.command_run
    mock_run.assert_called_once()


# ── file-existence strategy ──────────────────────────────────────────────

def test_file_write_all_exist_and_nonempty(tmp_path):
    f = tmp_path / "out.txt"
    f.write_text("hello")
    spec = _spec("把结果保存到 out.txt")
    vr = auto_verify(spec, _result(), work_dir=str(tmp_path))
    assert vr.passed is True
    assert vr.command_run == ""  # no command run for this strategy


def test_file_write_missing_file_fails(tmp_path):
    spec = _spec("把结果保存到 nope.txt")
    vr = auto_verify(spec, _result(), work_dir=str(tmp_path))
    assert vr.passed is False
    assert "nope.txt" in vr.details


def test_file_write_empty_file_fails(tmp_path):
    (tmp_path / "empty.txt").write_text("")
    spec = _spec("生成 empty.txt")
    vr = auto_verify(spec, _result(), work_dir=str(tmp_path))
    assert vr.passed is False
    assert "empty" in vr.details


def test_file_write_no_paths_in_goal_fails(tmp_path):
    spec = _spec("随便保存一下")
    vr = auto_verify(spec, _result(), work_dir=str(tmp_path))
    assert vr.passed is False


# ── generic fallback ─────────────────────────────────────────────────────

def test_generic_done_with_output_passes():
    vr = auto_verify(_spec("总结一下"), _result(status="done", output="blah"))
    assert vr.passed is True
    assert vr.command_run == ""


def test_generic_empty_output_fails():
    vr = auto_verify(_spec("总结一下"), _result(status="done", output="   "))
    assert vr.passed is False


def test_generic_error_status_fails():
    vr = auto_verify(_spec("总结一下"), _result(status="timeout", output="x"))
    assert vr.passed is False
    assert "timeout" in vr.details


# ── timeout handling ─────────────────────────────────────────────────────

@patch("tools.delegate_runtime.verify.subprocess.run")
def test_command_timeout_fails_gracefully(mock_run):
    import subprocess as sp

    mock_run.side_effect = sp.TimeoutExpired(cmd="x", timeout=60)
    spec = _spec("do it", verify_command="sleep 999")
    vr = auto_verify(spec, _result(), timeout=60)
    assert vr.passed is False
    assert "timed out" in vr.details


# ── public surface ───────────────────────────────────────────────────────

def test_exported_on_package():
    import tools.delegate_runtime as rt

    assert rt.auto_verify is auto_verify
    assert rt.VerifyResult is VerifyResult
    assert "auto_verify" in rt.__all__
    assert "VerifyResult" in rt.__all__

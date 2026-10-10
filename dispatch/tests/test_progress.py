#!/usr/bin/env python3
"""Unit tests for tools.delegate_runtime.progress.wait_with_progress."""

import pytest

from tools.delegate_runtime.backend import (
    BackendError,
    SubagentResult,
    SubagentState,
)
from tools.delegate_runtime.progress import wait_with_progress


def _state(status, subagent_id="run-1"):
    return SubagentState(
        subagent_id=subagent_id,
        agent_id="leaf",
        status=status,
        started_at=0.0,
    )


def _result(status="done"):
    return SubagentResult(subagent_id="run-1", status=status, output="ok")


class _ScriptedBackend:
    """Mock backend driven by pre-programmed status/result sequences."""

    def __init__(self, statuses, result=None):
        self._statuses = list(statuses)
        self._result = result
        self.sleep_calls = []

    def get_status(self, subagent_id):
        if not self._statuses:
            return _state("running")
        return self._statuses.pop(0)

    def get_result(self, subagent_id):
        return self._result

    def fake_sleep(self, seconds):
        self.sleep_calls.append(seconds)


def test_callback_fires_on_first_state_and_on_changes():
    seen = []
    backend = _ScriptedBackend(
        [_state("running"), _state("running"), _state("done")],
        result=_result(),
    )
    result = wait_with_progress(
        backend,
        "run-1",
        poll_interval=0,
        timeout=60,
        on_progress=seen.append,
        sleep_fn=backend.fake_sleep,
    )
    # first "running" + change to "done"; the duplicate "running" is silent
    assert [s.status for s in seen] == ["running", "done"]
    assert result.output == "ok"
    # polled twice before the terminal status (2 sleeps)
    assert backend.sleep_calls == [0, 0]


def test_works_without_callback():
    backend = _ScriptedBackend([_state("running"), _state("done")], result=_result())
    result = wait_with_progress(
        backend, "run-1", poll_interval=0, sleep_fn=backend.fake_sleep
    )
    assert result.status == "done"


def test_terminal_error_status_still_returns_result():
    backend = _ScriptedBackend(
        [_state("running"), _state("error")], result=_result(status="error")
    )
    result = wait_with_progress(
        backend, "run-1", poll_interval=0, sleep_fn=backend.fake_sleep
    )
    assert result.status == "error"


def test_timeout_raises_timeout_error():
    backend = _ScriptedBackend([_state("running")] * 100)
    with pytest.raises(TimeoutError):
        wait_with_progress(
            backend,
            "run-1",
            poll_interval=0,
            timeout=0,  # deadline already passed: raises without real sleeping
            sleep_fn=backend.fake_sleep,
        )


def test_disappearing_task_raises_backend_error():
    backend = _ScriptedBackend([None] * 10)
    with pytest.raises(BackendError, match="disappeared"):
        wait_with_progress(
            backend, "run-1", poll_interval=0, sleep_fn=backend.fake_sleep
        )
    # 5 consecutive Nones trigger the error
    assert len(backend.sleep_calls) == 4


def test_terminal_without_result_raises_backend_error():
    backend = _ScriptedBackend([_state("done")], result=None)
    with pytest.raises(BackendError, match="get_result"):
        wait_with_progress(
            backend, "run-1", poll_interval=0, sleep_fn=backend.fake_sleep
        )


def test_transient_none_then_recovery():
    # a few Nones (e.g. flaky network) do not abort the wait
    backend = _ScriptedBackend(
        [None, None, _state("running"), _state("done")], result=_result()
    )
    result = wait_with_progress(
        backend, "run-1", poll_interval=0, sleep_fn=backend.fake_sleep
    )
    assert result.output == "ok"

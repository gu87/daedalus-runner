#!/usr/bin/env python3
"""Unit tests for tools.delegate_runtime.execution.build_execution_entry."""

from __future__ import annotations

from tools.delegate_runtime.execution import build_execution_entry


def test_build_execution_entry_basic():
    entry = build_execution_entry(task_index=0, status="success", summary="done")
    assert entry == {
        "task_index": 0,
        "status": "success",
        "summary": "done",
        "api_calls": 0,
        "duration_seconds": 0.0,
    }
    assert "error" not in entry


def test_build_execution_entry_with_error():
    entry = build_execution_entry(
        task_index=1,
        status="error",
        summary=None,
        error="boom",
        api_calls=3,
        duration_seconds=1.5,
    )
    assert entry["task_index"] == 1
    assert entry["status"] == "error"
    assert entry["summary"] is None
    assert entry["error"] == "boom"
    assert entry["api_calls"] == 3
    assert entry["duration_seconds"] == 1.5


def test_build_execution_entry_with_extra():
    entry = build_execution_entry(
        task_index=2,
        status="success",
        summary="ok",
        extra={"note": "n1", "child_role": "worker"},
    )
    assert entry["note"] == "n1"
    assert entry["child_role"] == "worker"
    assert entry["task_index"] == 2


def test_build_execution_entry_extra_overrides_base():
    entry = build_execution_entry(
        task_index=3,
        status="success",
        summary="orig",
        extra={"summary": "overridden", "api_calls": 99},
    )
    assert entry["summary"] == "overridden"
    assert entry["api_calls"] == 99


def test_build_execution_entry_extra_none_identity():
    entry = build_execution_entry(task_index=4, status="running")
    assert "error" not in entry
    assert "extra" not in entry
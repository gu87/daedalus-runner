#!/usr/bin/env python3
"""Unit tests for build_execution_result_payload in tools.delegate_runtime.execution."""

from tools.delegate_runtime.execution import build_execution_result_payload


def test_normal_sorts_results_by_task_index():
    results = [
        {"task_index": 2, "status": "ok"},
        {"task_index": 0, "status": "ok"},
        {"task_index": 1, "status": "ok"},
    ]

    payload = build_execution_result_payload(
        results, started_at=0.0, finished_at=1.234
    )

    assert [entry["task_index"] for entry in payload["results"]] == [0, 1, 2]
    assert payload["total_duration_seconds"] == 1.23
    # original sequence must not be mutated
    assert [entry["task_index"] for entry in results] == [2, 0, 1]


def test_empty_results():
    payload = build_execution_result_payload([], started_at=10.0, finished_at=10.5)

    assert payload["results"] == []
    assert payload["total_duration_seconds"] == 0.5


def test_sort_results_false_preserves_input_order():
    results = [
        {"task_index": 2, "status": "ok"},
        {"task_index": 0, "status": "ok"},
        {"task_index": 1, "status": "ok"},
    ]

    payload = build_execution_result_payload(
        results,
        started_at=0.0,
        finished_at=2.0,
        sort_results=False,
    )

    assert [entry["task_index"] for entry in payload["results"]] == [2, 0, 1]
    assert payload["total_duration_seconds"] == 2.0

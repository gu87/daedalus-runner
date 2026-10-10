import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from tools.delegate_runtime.backend import DaedalusBackend, TaskSpec


def test_running_tasks_hold_slots_until_completion(monkeypatch):
    backend = DaedalusBackend()
    lock = threading.Lock()
    two_started = threading.Event()
    third_started = threading.Event()
    complete = threading.Event()
    started = []
    def request(method, path, payload=None):
        if method == "POST":
            with lock:
                started.append(payload["goal"])
                run_id = str(len(started))
                if len(started) == 2:
                    two_started.set()
                if len(started) == 3:
                    third_started.set()
            return {"run_id": run_id}
        return {"status": "completed" if complete.is_set() else "running"}
    monkeypatch.setattr(backend, "_request", request)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = [pool.submit(backend.dispatch, TaskSpec("leaf", str(i))) for i in range(2)]
        assert two_started.wait(2)
        for future in first:
            future.result(timeout=2)
        third = pool.submit(backend.dispatch, TaskSpec("leaf", "third"))
        try:
            assert not third_started.wait(0.2)
        finally:
            complete.set()
        assert third.result(timeout=3) == "3"


def test_failed_dispatch_releases_slot(monkeypatch):
    backend = DaedalusBackend(max_concurrent=1)
    def request(method, path, payload=None):
        if payload["goal"] == "fail":
            raise RuntimeError("dispatch failed")
        return {"run_id": "ok"}
    monkeypatch.setattr(backend, "_request", request)
    with pytest.raises(RuntimeError):
        backend.dispatch(TaskSpec("leaf", "fail"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(backend.dispatch, TaskSpec("leaf", "ok")).result(timeout=2) == "ok"


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled", "timed_out"])
@pytest.mark.parametrize("read_method", ["get_status", "get_result"])
def test_terminal_status_releases_slot_once(monkeypatch, status, read_method):
    backend = DaedalusBackend(max_concurrent=1)
    started = []
    def request(method, path, payload=None):
        if method == "POST":
            started.append(payload["goal"])
            return {"run_id": str(len(started))}
        return {"status": status}
    monkeypatch.setattr(backend, "_request", request)
    run_id = backend.dispatch(TaskSpec("leaf", "first"))
    getattr(backend, read_method)(run_id)
    getattr(backend, read_method)(run_id)
    assert backend.dispatch(TaskSpec("leaf", "second")) == "2"
    assert not backend._task_slots.acquire(blocking=False)


@pytest.mark.parametrize("limit", [0, -1])
def test_invalid_concurrency_limit(limit):
    with pytest.raises(ValueError, match="max_concurrent"):
        DaedalusBackend(max_concurrent=limit)

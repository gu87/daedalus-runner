#!/usr/bin/env python3
"""Progress-visible waiting for delegated subagent tasks.

The plain ``get_result()`` polling loop tells the caller nothing until the
task is finished. :func:`wait_with_progress` instead polls ``get_status()``
and reports every status transition through an optional callback, so a host
can show progress (spinners, logs, UI updates) while the subagent works.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from tools.delegate_runtime.backend import (
    BackendError,
    BackendProtocol,
    SubagentResult,
    SubagentState,
)

#: Statuses that end the wait loop. Anything else (e.g. "running") keeps polling.
TERMINAL_STATUSES = frozenset({"done", "timeout", "cancelled", "error"})

#: get_status() returning None this many times in a row means the task is gone.
_MAX_CONSECUTIVE_NONE = 5


def wait_with_progress(
    backend: BackendProtocol,
    subagent_id: str,
    *,
    poll_interval: float = 3.0,
    timeout: float = 300.0,
    on_progress: Optional[Callable[[SubagentState], None]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> SubagentResult:
    """Poll ``backend.get_status`` until *subagent_id* reaches a terminal status.

    Calls ``on_progress(state)`` for the first observed state and on every
    subsequent status change, then returns ``backend.get_result(subagent_id)``.

    Raises:
        TimeoutError: if *timeout* seconds elapse before a terminal status.
        BackendError: if the task disappears (``get_status`` returns ``None``
            repeatedly) or no result is available after a terminal status.
    """
    deadline = time.monotonic() + timeout
    last_status: Optional[str] = None
    consecutive_none = 0

    while True:
        state = backend.get_status(subagent_id)
        if state is None:
            consecutive_none += 1
            if consecutive_none >= _MAX_CONSECUTIVE_NONE:
                raise BackendError(
                    f"task {subagent_id!r} disappeared "
                    "(get_status returned None repeatedly)"
                )
        else:
            consecutive_none = 0
            if on_progress is not None and state.status != last_status:
                on_progress(state)
            last_status = state.status
            if state.status in TERMINAL_STATUSES:
                result = backend.get_result(subagent_id)
                if result is None:
                    raise BackendError(
                        f"task {subagent_id!r} reached terminal status "
                        f"{state.status!r} but get_result() returned None"
                    )
                return result
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"timed out waiting for {subagent_id!r} after {timeout} seconds"
            )
        sleep_fn(poll_interval)

# taskflow/core/cancellation.py

"""Cooperative cancellation for running task functions.

Python cannot kill a thread. `asyncio.wait_for` around `run_in_executor`
cancels the future, not the work: the thread keeps running to completion,
still holding a pool slot. That is a known limitation of the timeout path
(see WorkerPool._execute_task) and it applies just as much to cancellation -
so a running task can only stop if it agrees to.

Task functions opt in by checking `is_cancelled()`:

    @task
    def process_batch(rows):
        for row in rows:
            if is_cancelled():
                return {"stopped_early": True}
            handle(row)

or by calling `raise_if_cancelled()`, which the worker turns into a
CANCELLED task rather than a failure.

A task that never checks is not broken - it simply runs to completion, and
the worker records CANCELLED afterwards instead of COMPLETED. The difference
is only how quickly the slot is freed.

The flag is a threading.Event held in a thread-local, because task functions
run in a ThreadPoolExecutor and are ordinary synchronous code: they cannot
await a backend lookup. WorkerPool sets the event from the async side (see
its cancellation poller) and the function just reads it.
"""

import threading

_local = threading.local()


class TaskCancelled(Exception):
    """Raised by raise_if_cancelled() when cancellation has been requested.

    WorkerPool treats this as a clean stop, not a failure: no retry, no
    error message, terminal status CANCELLED.
    """


def is_cancelled() -> bool:
    """Has cancellation been requested for the task on this thread?

    False anywhere outside a running task, so a task function stays callable
    directly from a test or the REPL.
    """
    event = getattr(_local, "event", None)
    return event is not None and event.is_set()


def raise_if_cancelled() -> None:
    """Stop now if cancellation has been requested."""
    if is_cancelled():
        raise TaskCancelled()


def _set_event(event: "threading.Event | None") -> None:
    """Bind the flag for the current thread. Called by WorkerPool only."""
    _local.event = event

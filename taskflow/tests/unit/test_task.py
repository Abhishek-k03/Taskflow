import json
from datetime import UTC, datetime
from queue import PriorityQueue

import pytest

from taskflow.core.task import Task, TaskPriority, TaskStatus


def test_priority_enum_values_order_critical_first():
    # CRITICAL must sort lowest (0) since PriorityQueue is a min-heap and
    # CRITICAL is meant to be dequeued first.
    assert TaskPriority.CRITICAL.value == 0
    assert TaskPriority.CRITICAL.value < TaskPriority.HIGH.value
    assert TaskPriority.HIGH.value < TaskPriority.NORMAL.value
    assert TaskPriority.NORMAL.value < TaskPriority.LOW.value


def test_priority_queue_orders_by_priority_then_fifo():
    pq = PriorityQueue()
    first_normal = Task(priority=TaskPriority.NORMAL.value, func_name="a")
    second_normal = Task(priority=TaskPriority.NORMAL.value, func_name="b")
    critical = Task(priority=TaskPriority.CRITICAL.value, func_name="c")

    pq.put(first_normal)
    pq.put(second_normal)
    pq.put(critical)

    assert pq.get().func_name == "c"  # CRITICAL first regardless of order
    assert pq.get().func_name == "a"  # then FIFO within the same priority
    assert pq.get().func_name == "b"


def test_post_init_coerces_priority_enum_to_int():
    task = Task(priority=TaskPriority.HIGH, func_name="x")
    assert task.priority == 1
    assert isinstance(task.priority, int)


def test_mark_queued():
    task = Task(priority=2, func_name="x")
    assert task.status == TaskStatus.PENDING
    task.mark_queued()
    assert task.status == TaskStatus.QUEUED


def test_mark_running_sets_aware_started_at():
    task = Task(priority=2, func_name="x")
    task.mark_running()
    assert task.status == TaskStatus.RUNNING
    assert task.started_at is not None
    assert task.started_at.tzinfo is not None


def test_mark_completed_stores_result():
    task = Task(priority=2, func_name="x")
    task.mark_completed(result=42)
    assert task.status == TaskStatus.COMPLETED
    assert task.result == 42
    assert task.completed_at.tzinfo is not None


def test_mark_failed_stores_error():
    task = Task(priority=2, func_name="x")
    task.mark_failed("boom")
    assert task.status == TaskStatus.FAILED
    assert task.error == "boom"
    assert task.completed_at.tzinfo is not None


def test_mark_retrying_does_not_increment_retry_count():
    # retry_count is owned by the caller (WorkerPool), which increments it
    # BEFORE calling mark_retrying() to decide retry-vs-fail. Regression test
    # for the double-increment bug this fixed.
    task = Task(priority=2, func_name="x")
    task.retry_count = 1
    task.mark_retrying()
    assert task.status == TaskStatus.RETRYING
    assert task.retry_count == 1


def test_can_retry():
    task = Task(priority=2, func_name="x", max_retries=3)
    assert task.can_retry() is True
    task.retry_count = 3
    assert task.can_retry() is False


def test_created_at_is_aware_utc_by_default():
    task = Task(priority=2, func_name="x")
    assert task.created_at.tzinfo is not None
    assert task.created_at.utcoffset() == datetime.now(UTC).utcoffset()


def test_to_dict_includes_all_fields_needed_for_the_api():
    task = Task(
        priority=1,
        func_name="add_numbers",
        args=(1, 2),
        kwargs={"x": 1},
        max_retries=5,
        timeout=30,
    )
    task.scheduled_at = datetime.now(UTC)
    d = task.to_dict()

    for key in (
        "task_id",
        "func_name",
        "args",
        "kwargs",
        "status",
        "priority",
        "created_at",
        "scheduled_at",
        "started_at",
        "completed_at",
        "result",
        "error",
        "retry_count",
        "max_retries",
    ):
        assert key in d, f"to_dict() is missing '{key}'"

    assert d["func_name"] == "add_numbers"
    assert d["args"] == (1, 2)
    assert d["kwargs"] == {"x": 1}
    assert d["max_retries"] == 5
    assert d["scheduled_at"] is not None
    # started_at/completed_at are still None pre-execution
    assert d["started_at"] is None
    assert d["completed_at"] is None


def test_to_dict_created_at_serializes_with_utc_offset():
    task = Task(priority=2, func_name="x")
    assert task.to_dict()["created_at"].endswith("+00:00")


# --- Serialization round trip (the Phase 2 blocker) ---------------------


def _json_round_trip(task: Task) -> Task:
    """Simulate what a Redis stream would actually do: to_dict(), through
    real JSON (not just a Python dict copy), then from_dict()."""
    payload = json.loads(json.dumps(task.to_dict()))
    return Task.from_dict(payload)


def test_round_trip_preserves_core_fields():
    original = Task(
        priority=1,
        func_name="add_numbers",
        args=(1, 2),
        kwargs={"x": 1},
        max_retries=5,
        timeout=30,
        depends_on=["other-task-id"],
        cron_expression="*/5 * * * *",
    )
    restored = _json_round_trip(original)

    assert restored.task_id == original.task_id
    assert restored.func_name == original.func_name
    assert restored.args == original.args
    assert restored.kwargs == original.kwargs
    assert restored.priority == original.priority
    assert restored.max_retries == original.max_retries
    assert restored.timeout == original.timeout
    assert restored.depends_on == original.depends_on
    assert restored.cron_expression == original.cron_expression
    assert restored.status == original.status


def test_round_trip_preserves_args_as_a_tuple():
    # JSON has no tuple type - round-tripping through it turns args into a
    # list unless from_dict() explicitly converts it back.
    original = Task(priority=2, func_name="x", args=(1, "two", 3.0))
    restored = _json_round_trip(original)
    assert isinstance(restored.args, tuple)
    assert restored.args == (1, "two", 3.0)


def test_round_trip_preserves_aware_timestamps():
    original = Task(priority=2, func_name="x")
    original.mark_running()
    original.mark_completed(result=1)

    restored = _json_round_trip(original)

    assert restored.created_at == original.created_at
    assert restored.started_at == original.started_at
    assert restored.completed_at == original.completed_at
    assert restored.started_at.tzinfo is not None
    assert restored.completed_at.tzinfo is not None


def test_round_trip_preserves_status_and_result():
    original = Task(priority=2, func_name="x")
    original.mark_completed(result={"nested": [1, 2, 3]})

    restored = _json_round_trip(original)

    assert restored.status == TaskStatus.COMPLETED
    assert restored.result == {"nested": [1, 2, 3]}


def test_round_trip_preserves_error_and_retry_count():
    original = Task(priority=2, func_name="x", max_retries=3)
    original.retry_count = 2
    original.mark_failed("boom")

    restored = _json_round_trip(original)

    assert restored.status == TaskStatus.FAILED
    assert restored.error == "boom"
    assert restored.retry_count == 2
    assert restored.max_retries == 3


def test_round_trip_gives_a_fresh_sequence_not_the_original():
    # sequence is deliberately excluded from the wire format - see
    # to_dict()'s docstring. A round-tripped task is a "new" task as far as
    # this process's local FIFO tie-breaking is concerned.
    original = Task(priority=2, func_name="x")
    restored = _json_round_trip(original)
    assert restored.sequence != original.sequence


def test_to_dict_rejects_non_json_serializable_result():
    task = Task(priority=2, func_name="x")
    task.mark_completed(result=object())  # arbitrary object, not JSON-safe

    with pytest.raises(TypeError, match="not JSON-serializable"):
        task.to_dict()


def test_to_dict_accepts_json_safe_result_types():
    for result in (None, 42, 3.14, "text", True, [1, 2], {"a": 1}):
        task = Task(priority=2, func_name="x")
        task.mark_completed(result=result)
        assert task.to_dict()["result"] == result

from datetime import UTC, datetime
from queue import PriorityQueue

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

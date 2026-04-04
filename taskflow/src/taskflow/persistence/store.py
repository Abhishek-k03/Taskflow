# taskflow/persistence/store.py

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..core.task import Task, TaskStatus, now_utc
from .models import TaskEventRecord, TaskRecord

_TIMESTAMP_FIELDS = ("created_at", "scheduled_at", "started_at", "completed_at")

# to_dict() keys that are not columns on `tasks`. None today, but the read
# path reconstructs tasks by column name, so this keeps the two directions
# honest if the wire format and the schema ever diverge.
_COLUMN_NAMES = tuple(c.name for c in TaskRecord.__table__.columns)


class TaskStore:
    """Postgres: the durable record of every task.

    Writes are dual-write - every enqueue()/update_task() upserts into
    `tasks` and appends to `task_events` in one transaction. This raises on
    failure rather than swallowing errors; the queue backend decides whether
    that's fatal (it isn't - it logs and continues, so a Postgres outage
    degrades history rather than stopping task execution).

    Reads are what make that durability visible. Redis holds the hot path
    (queued and in-flight work) and only a bounded recent window of finished
    tasks; Postgres holds all of it, which is why the list and detail
    endpoints prefer this store when one is configured.

    The asymmetry between the two directions is deliberate: because writes
    are best-effort, a row can be missing here while the task genuinely
    exists in the queue. Callers therefore treat a miss as "not found here",
    not "does not exist" - see routes.py, which falls back to the queue
    backend.
    """

    def __init__(self, sessionmaker: async_sessionmaker):
        self._sessionmaker = sessionmaker

    async def persist(self, task: Task) -> None:
        data = task.to_dict()

        # to_dict() is the REST/WS wire format, so timestamps are ISO
        # strings there - the DB columns want real datetimes back, parsed
        # the same way Task.from_dict() does.
        columns = dict(data)
        for field in _TIMESTAMP_FIELDS:
            if columns[field] is not None:
                columns[field] = datetime.fromisoformat(columns[field])

        async with self._sessionmaker() as session:
            async with session.begin():
                upsert = pg_insert(TaskRecord).values(**columns)
                upsert = upsert.on_conflict_do_update(
                    index_elements=[TaskRecord.task_id],
                    set_={k: v for k, v in columns.items() if k != "task_id"},
                )
                await session.execute(upsert)

                session.add(
                    TaskEventRecord(
                        task_id=task.task_id,
                        event_type=data["status"],
                        timestamp=now_utc(),
                        task_snapshot=data,
                    )
                )

    async def get_task(self, task_id: str) -> Optional[Task]:
        """One task by id, or None if this store has never seen it."""
        async with self._sessionmaker() as session:
            record = await session.get(TaskRecord, task_id)
            return _to_task(record) if record else None

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
    ) -> list[Task]:
        """Newest first, optionally filtered by status.

        Ordering and limiting happen in SQL rather than in Python: the whole
        point of reading from Postgres is that it holds far more history than
        fits in a process, so `SELECT *` then slice would defeat it.
        """
        query = select(TaskRecord)
        if status is not None:
            query = query.where(TaskRecord.status == status.value)
        # task_id breaks ties: two tasks submitted in the same microsecond
        # would otherwise come back in an order Postgres is free to vary
        # between calls, which makes paging over them unreliable.
        query = query.order_by(
            TaskRecord.created_at.desc(), TaskRecord.task_id.desc()
        ).limit(limit)

        async with self._sessionmaker() as session:
            result = await session.execute(query)
            return [_to_task(record) for record in result.scalars()]


def _to_task(record: TaskRecord) -> Task:
    """Rebuild a Task from its row.

    Goes through Task.from_dict() rather than mapping fields by hand, so
    there is exactly one deserializer to keep correct - the columns were
    written from to_dict() in the first place. That means handing it ISO
    strings, since from_dict() parses the wire format and the DB gives back
    real datetimes.
    """
    data = {name: getattr(record, name) for name in _COLUMN_NAMES}
    for field in _TIMESTAMP_FIELDS:
        if data[field] is not None:
            data[field] = data[field].isoformat()
    return Task.from_dict(data)

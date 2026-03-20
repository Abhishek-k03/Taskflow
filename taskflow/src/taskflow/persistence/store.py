# taskflow/persistence/store.py

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..core.task import Task, now_utc
from .models import TaskEventRecord, TaskRecord

_TIMESTAMP_FIELDS = ("created_at", "scheduled_at", "started_at", "completed_at")


class TaskStore:
    """Postgres dual-write.

    Every TaskQueue.enqueue()/update_task() call persists here: an upsert
    into `tasks` plus an append-only row in `task_events`, in one
    transaction. This raises on failure rather than swallowing errors -
    TaskQueue decides whether that's fatal (currently: no, it's just logged,
    since the in-memory queue is still authoritative for reads at this
    stage).
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

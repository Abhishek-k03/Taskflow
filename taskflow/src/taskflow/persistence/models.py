# taskflow/persistence/models.py

"""SQLAlchemy models for the Postgres durable store.

These mirror Task.to_dict()'s shape (see core/task.py) - that dict is the
wire format everything else is built on, and these tables are just another
consumer of it. `tasks` is upserted on every enqueue/update_task call;
`task_events` is an append-only row per write, giving a full history even
after the `tasks` row itself has moved on to a later status.

`periodic_tasks` is defined here now but not yet written to - periodic
definitions move here in a later step (Sequencing step 16), once the
scheduler can read its schedule back from Postgres instead of an in-process
dict that's lost on every restart.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Every Task timestamp is timezone-aware (see core/task.py's now_utc()) -
    # map datetime columns to TIMESTAMPTZ everywhere by default instead of
    # relying on each mapped_column() to opt in and risk one being missed.
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class TaskRecord(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    func_name: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    kwargs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    result: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSONB, nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(nullable=False, default=3)
    timeout: Mapped[int | None] = mapped_column(nullable=True)
    depends_on: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    cron_expression: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        # Backs the list endpoint's status filter + created_at ordering.
        Index("ix_tasks_status_created_at", "status", "created_at"),
        # And the unfiltered case, which the dashboard hits on every load.
        # Without this, "newest 100 of everything" sorts the whole table -
        # fine at 50 rows, not at 50,000, which is the size Postgres exists
        # to hold in the first place.
        Index("ix_tasks_created_at", "created_at"),
    )


class PeriodicTaskRecord(Base):
    __tablename__ = "periodic_tasks"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    func_name: Mapped[str] = mapped_column(String, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String, nullable=False)
    args: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    kwargs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(nullable=False)
    max_retries: Mapped[int] = mapped_column(nullable=False, default=3)
    timeout: Mapped[int | None] = mapped_column(nullable=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    next_run: Mapped[datetime] = mapped_column(nullable=False)
    last_run: Mapped[datetime | None] = mapped_column(nullable=True)
    run_count: Mapped[int] = mapped_column(nullable=False, default=0)


class TaskEventRecord(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        String, ForeignKey("tasks.task_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(nullable=False)
    task_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (Index("ix_task_events_task_id", "task_id"),)

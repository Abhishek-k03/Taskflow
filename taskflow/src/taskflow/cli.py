# taskflow/cli.py

"""Command-line entrypoint.

`taskflow` serves the app (role picked up from TASKFLOW_ROLE). `taskflow
tasks list` is a smoke check for TASKFLOW_TASK_MODULES that doesn't start a
server - a typo there yields an empty registry with no obvious cause once
you're staring at 404s on every task submission.
"""

import argparse
import logging
import sys

import uvicorn

from .app import create_app
from .bootstrap import import_task_modules
from .config import Settings
from .observability import configure_logging


def _serve(settings: Settings) -> None:
    configure_logging(settings.log_level, settings.json_logs)
    app = create_app(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )


def _tasks_list(settings: Settings) -> None:
    try:
        registered = import_task_modules(settings.task_modules)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"{len(registered)} tasks registered:")
    for name in registered:
        print(f"  {name}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="taskflow")
    subparsers = parser.add_subparsers(dest="command")

    tasks_parser = subparsers.add_parser("tasks", help="Inspect the task registry")
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command")
    tasks_subparsers.add_parser("list", help="List registered task functions")

    args = parser.parse_args()
    settings = Settings()

    if args.command == "tasks" and args.tasks_command == "list":
        _tasks_list(settings)
        return

    _serve(settings)


if __name__ == "__main__":
    main()

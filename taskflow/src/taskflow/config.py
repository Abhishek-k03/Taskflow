# taskflow/config.py

import json
from enum import Enum
from typing import Annotated, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Role(str, Enum):
    """Which parts of the system this process runs.

    One image, three deployables: `api` serves HTTP and enqueues, `worker`
    executes tasks, `scheduler` fires periodic tasks. `all` runs everything in
    one process, which is the local-dev path and today's behaviour.
    """

    API = "api"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    ALL = "all"


class Settings(BaseSettings):
    """Application settings, read from TASKFLOW_-prefixed env vars."""

    model_config = SettingsConfigDict(
        env_prefix="TASKFLOW_",
        env_file=".env",
        extra="ignore",
    )

    role: Role = Role.ALL

    # Worker pool
    num_workers: int = 4

    # Queue
    max_queue_size: int = 0  # 0 means unbounded

    # Task defaults
    default_max_retries: int = 3
    default_timeout: Optional[int] = None

    # Modules imported at startup so their @task decorators register functions.
    # A typo here yields an empty registry and every submission 404s, so the
    # `taskflow tasks` command exists to check this without starting a server.
    task_modules: Annotated[list[str], NoDecode] = ["taskflow.tasks.builtin"]

    # Browsers reject allow_origins=["*"] together with allow_credentials=True,
    # so this has to be an explicit list.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    log_level: str = "INFO"

    @field_validator("task_modules", "cors_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value):
        """Accept `a,b` as well as JSON `["a","b"]`, since comma-separated is
        what you actually want to type in a compose file. These fields are
        NoDecode, so parsing the JSON form is ours to do."""
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value.startswith("["):
            return json.loads(value)
        return [item.strip() for item in value.split(",") if item.strip()]


settings = Settings()

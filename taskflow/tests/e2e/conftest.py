import os

import pytest
import requests

E2E_URL = os.environ.get("TASKFLOW_E2E_URL", "http://localhost:8000")


@pytest.fixture(scope="session", autouse=True)
def _require_live_server():
    """Skip the whole e2e suite instead of failing every test when no
    server is running - this is what makes `pytest` safe to run bare."""
    try:
        requests.get(f"{E2E_URL}/health", timeout=2)
    except requests.exceptions.ConnectionError:
        pytest.skip(f"No TaskFlow server reachable at {E2E_URL}")

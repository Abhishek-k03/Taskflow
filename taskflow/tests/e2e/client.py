"""The HTTP client the end-to-end tests share.

A plain `requests.post` stopped working the moment API key auth landed: every
mutating call in this suite started returning 401, and because the suite is
excluded by default (`addopts = -m 'not e2e and not slow'`) nothing said so.
Routing all of them through one authenticated session means the key is
configured in exactly one place, and adding a test cannot quietly forget it.
"""

import os

import requests

BASE_URL = f"{os.environ.get('TASKFLOW_E2E_URL', 'http://localhost:8000')}/api/v1"

# Matches the default docker-compose sets, so `pytest -m e2e` against a stack
# started with `docker compose up` needs no extra environment.
API_KEY = os.environ.get("TASKFLOW_API_KEY", "local-dev-key")

api = requests.Session()
api.headers.update({"X-API-Key": API_KEY})

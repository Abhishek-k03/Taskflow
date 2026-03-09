# syntax=docker/dockerfile:1

# ---- builder ----
FROM python:3.13-slim AS builder

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# pip needs the full source tree to build the wheel (pyproject.toml alone
# is not enough - setuptools has to discover the src/ packages), so this
# layer is invalidated on every source change, not just dependency changes.
COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# ---- runtime ----
FROM python:3.13-slim AS runtime

RUN useradd --create-home --uid 1000 taskflow

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY main.py ./main.py

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER taskflow

EXPOSE 8000

# The `taskflow` console script reads TASKFLOW_* settings (role, host, port,
# reload) at startup instead of the hardcoded values `uvicorn main:app` would
# use. main.py is still here for local dev (`uvicorn main:app --reload`).
CMD ["taskflow"]

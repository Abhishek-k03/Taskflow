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

# Runs uvicorn directly (not `python main.py`), which sidesteps main.py's
# hardcoded reload=True - that flag only fires inside the __main__ guard.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

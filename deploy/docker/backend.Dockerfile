# syntax=docker/dockerfile:1

FROM python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY backend ./backend
COPY tools/__init__.py \
    tools/check_worker_health.py \
    tools/create_admin.py \
    tools/local_demo.py \
    tools/manage_admin.py \
    tools/prod_init.py \
    tools/provision_agent_cert.py \
    tools/provision_compose_certs.py \
    tools/replay_failure.py \
    tools/run_detection_worker.py \
    tools/run_event_storage_worker.py \
    tools/run_storage_lifecycle_worker.py \
    tools/secure_files.py \
    tools/seed_presentation_demo.py \
    tools/seed_safety.py \
    tools/verify_presentation_demo.py \
    ./tools/
COPY mappings ./mappings
COPY migrations ./migrations
COPY rules ./rules
COPY schemas ./schemas

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

USER app

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

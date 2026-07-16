# Backend image. Three targets:
#   dev    — dev + geometry deps so `docker compose exec app pytest` covers everything.
#   prod   — API runtime deps only; used by Kamal on deploy. NO OCP/vtk (~160 MB):
#            interrogation runs on Celery workers only (DECISIONS.md 2026-07-16).
#   worker — prod deps + the geometry group (OCP) + libgl1: OCP links libGL even
#            headless via its vtk linkage (GEOMETRY.md §0, M4.0 linux run).
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /uvx /bin/
# Production processes never run as root: the API serves untrusted uploads and
# the worker parses untrusted STEP files through OCP/VTK. Fixed UID/GID; the
# dev target stays root so `docker compose exec` remains frictionless.
RUN groupadd --gid 10001 tolera && \
    useradd --uid 10001 --gid tolera --no-create-home --shell /usr/sbin/nologin tolera
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./

FROM base AS dev
# libgl1 for the geometry group (default-groups) when the dev image runs on linux.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS prod
# --no-default-groups: dev AND geometry stay out of the API image.
RUN uv sync --frozen --no-default-groups
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
USER tolera
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-default-groups --group geometry
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
USER tolera
CMD ["celery", "-A", "app.celery_app", "worker", "-Q", "celery,email", "--loglevel=INFO"]

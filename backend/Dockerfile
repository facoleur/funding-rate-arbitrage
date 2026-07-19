FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps first for cache efficiency
COPY backend/pyproject.toml backend/uv.lock* /app/
RUN uv sync --frozen --no-install-project --no-dev 2>/dev/null || uv sync --no-install-project --no-dev

# Now copy source
COPY backend/src /app/src
COPY backend/alembic.ini /app/alembic.ini

RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

# Default command overridden by docker-compose per service
CMD ["uv", "run", "uvicorn", "option_arb.main:app", "--host", "0.0.0.0", "--port", "8000"]

# syntax=docker/dockerfile:1

# The runtime base ships a system Python so the virtualenv symlink remains
# readable by the non-root application user. The previous uv-image-only runtime
# pointed the venv at /root/.local, which uid 10001 cannot traverse.
FROM ghcr.io/astral-sh/uv:bookworm-slim AS uv

FROM python:3.13-slim AS runtime

COPY --from=uv /usr/local/bin/uv /usr/local/bin/uv
COPY --from=uv /usr/local/bin/uvx /usr/local/bin/uvx

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_FROZEN=1 \
    UV_PYTHON=/usr/local/bin/python \
    UV_PYTHON_DOWNLOADS=never \
    DENDRO_DATA_DIR=/data \
    DENDRO_STATIC_DIR=/app/frontend/dist \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

COPY frontend/dist /app/frontend/dist

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /app /data
USER app

VOLUME ["/data"]
EXPOSE 8000
CMD ["/app/backend/.venv/bin/dendromatrix", "--host", "0.0.0.0", "--port", "8000"]

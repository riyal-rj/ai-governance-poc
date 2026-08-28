FROM python:3.12.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN python -m pip install "uv>=0.9,<1"

WORKDIR /app

# pyproject.toml + uv.lock are the only authoritative dependency source; no
# requirements.txt is kept in the repo so the two cannot drift.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN groupadd --system --gid 10001 finassist \
    && useradd --system --uid 10001 --gid finassist --home-dir /nonexistent finassist

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --chown=finassist:finassist src ./src
COPY --chown=finassist:finassist scripts ./scripts
COPY --chown=finassist:finassist migrations ./migrations

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "src.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

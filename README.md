# FinAssist

Phase 1A is the production-oriented FastAPI foundation for the governed FinAssist
PoC. It contains validated immutable configuration, explicit dependency injection,
bounded PostgreSQL and OPA startup/readiness checks, structured error contracts,
request correlation, Prometheus metrics, and graceful resource cleanup.

Business capabilities and LLM integrations are intentionally not part of this
phase.

## Run with Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Operational endpoints:

- `GET http://localhost:8000/health/live`
- `GET http://localhost:8000/health/ready`
- `GET http://localhost:8000/metrics`
- `GET http://localhost:8000/docs`

Stop the local stack without deleting its PostgreSQL volume:

```powershell
docker compose down
```

## Run the API from PowerShell

Start PostgreSQL with Docker. OPA's REST port is intentionally not published to
the host in `docker-compose.yml` — only the `api` container may reach it — so
this host-mode workflow runs OPA separately with its port published locally:

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
docker run --rm -d --name finassist-opa-dev -p 127.0.0.1:8181:8181 `
  -v "${PWD}/opa/policies:/policies:ro" openpolicyagent/opa:1.19.1-static `
  run --server --addr=0.0.0.0:8181 /policies

$env:FINASSIST_DATABASE__DSN = "postgresql://finassist:finassist_local_only@localhost:5432/finassist"
$env:FINASSIST_OPA__BASE_URL = "http://localhost:8181"
uv sync --locked --dev --link-mode copy
uv run python -m scripts.migrate
uv run uvicorn src.main:create_app --factory --host 127.0.0.1 --port 8000
```

Stop the standalone OPA container when done: `docker stop finassist-opa-dev`.

## Quality gates

```powershell
uv run ruff format --check src scripts tests
uv run ruff check src scripts tests
uv run mypy src scripts
uv run python -m compileall -q src scripts
uv run pytest
docker compose config --quiet
```

`pytest` runs with coverage enforced at a minimum of 90% (`--cov-fail-under=90`,
configured in `pyproject.toml`); a run below that threshold fails the gate.

Do not enable real payment execution in this foundation phase. The LLM, policy
decision, authentication, audit, kill-switch, and payment workflow boundaries are
introduced in later gated phases.

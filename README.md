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

Start PostgreSQL and OPA with Docker, then run the API on the host:

```powershell
Copy-Item .env.example .env
docker compose up -d postgres opa
$env:FINASSIST_DATABASE__DSN = "postgresql://finassist:finassist_local_only@localhost:5432/finassist"
$env:FINASSIST_OPA__BASE_URL = "http://localhost:8181"
uv sync --dev
uv run uvicorn src.main:create_app --factory --host 127.0.0.1 --port 8000
```

## Quality gates (excluding pytest in this phase)

```powershell
uv run ruff format --check src
uv run ruff check src
uv run mypy src
uv run python -m compileall -q src
docker compose config --quiet
```

Do not enable real payment execution in this foundation phase. The LLM, policy
decision, authentication, audit, kill-switch, and payment workflow boundaries are
introduced in later gated phases.

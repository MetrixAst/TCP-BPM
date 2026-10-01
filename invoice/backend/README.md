# invoice-backend

FastAPI backend for Metrix's TRC (shopping mall) invoice and payment registry.
Syncs invoices/payments from 1C (Nova COM/MCP relay or OData, per-tenant),
generates the formal invoice PDF, and sends it to tenants over WhatsApp
(Green API) via a Kafka-backed job queue. Serves both `invoice-admin` (mall
staff) and `invoice-client` (tenant-facing) frontends.

## Stack

FastAPI + SQLAlchemy + Alembic, Postgres, Python 3.12 (Docker) / 3.9+ locally.
Kafka for async WhatsApp send + webhook + payment-sync jobs (`app/workers/kafka_worker.py`).
Sentry for error tracking.

## Run locally

Requires a reachable Postgres instance.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: DATABASE_URL at minimum, plus SUPER_ADMIN_USERNAME/PASSWORD,
# NOVA_*/ONE_C_* if you need live 1C, GREEN_API_* for WhatsApp.

python run.py        # port 8004 by default, auto-reload
python run.py 8001   # or pick another port
```

Alembic migrations run automatically on startup (`app/main.py` lifespan).
API docs at `http://localhost:8004/docs`, health check at `/health`.

`app/core/config.py` loads exactly **one** env file, not merged, in this
order: `APP_ENV_FILE` → `.env` → `.env.development` → `.env.production` →
`.env.test`. A local `.env` fully shadows `.env.development` — copy the
whole file over, not just the one var you're changing.

### Kafka worker (optional, only if `KAFKA_ENABLED=true`)

```bash
python -m app.workers.kafka_worker
```

Consumes WhatsApp sends, incoming webhooks, and payment-sync jobs. Not
needed for basic local API/frontend development — WhatsApp sends will just
sit in the outbox/Kafka topic unprocessed without it.

### Tests

```bash
pytest tests/
```

Runs against an in-memory SQLite DB (see `tests/conftest.py`), no Postgres
needed.

## Docker

```bash
docker build -t invoice-backend .
docker run -p 8004:8004 --env-file .env.production invoice-backend
```

`docker-entrypoint.sh` runs `alembic upgrade head` then starts uvicorn.

## Layout

- `app/api/` — route handlers (`admin`, `catalog`, `payments`, `notifications`,
  `one_c`, `tenant_auth`, `webhooks`, `xlsx_import`).
- `app/services/` — 1C clients (Nova COM/MCP + OData), invoice PDF rendering
  and caching, WhatsApp/Green API sending, xlsx import.
- `app/models/` — SQLAlchemy models.
- `app/workers/kafka_worker.py` — async job consumer.
- `alembic/` — DB migrations.
- `tests/` — pytest suite, SQLite-backed.

## Security note

`.env.example` in this repo currently contains real-looking Nova credentials
(`NOVA_ADMIN_PASSWORD`, `NOVA_MCP_RELAY_API_KEY`) instead of placeholders —
worth rotating/redacting since it's committed to git history.

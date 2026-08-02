# DID — telecom numbering analytics

Internal service for loading and analyzing phone numbers from independent providers (Runexis, SipOut).

## Stack

- Backend: FastAPI, SQLAlchemy 2, Alembic, httpx, PostgreSQL
- Frontend: Next.js + TypeScript
- Compose: `db` + `backend` + `frontend`

## Documentation-driven providers

Uploaded HTML is the only source of truth for external APIs:

- [`docs/providers/runexis/raw/Runexis.html`](docs/providers/runexis/raw/Runexis.html)
- [`docs/providers/sipout/raw/SipOut.html`](docs/providers/sipout/raw/SipOut.html)

See also `*-contract.md`, `*-field-mapping.md`, `*-implementation-notes.md`.

**Locked product decisions:** SipOut `connected_list` → purchased; Runexis free/purchased sync capability-limited; SipOut `price` → `price_amount` only; soft-absence on; single `free_list` call.

## Local run (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000/docs
- UI: http://localhost:3000

Configure provider credentials in **Настройки**, then run sync.

## Local run (without Compose frontend)

```bash
# DB
docker compose up -d db

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
export DATABASE_URL=postgresql+psycopg://did:did@localhost:5432/did
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Architecture

See [architecture.md](architecture.md) and [db_schema.md](db_schema.md).

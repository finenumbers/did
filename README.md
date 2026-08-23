# DID — telecom numbering analytics

Internal admin console for loading and analyzing phone number inventory from independent providers (**SipOut**, **Runexis**, **UIS**, **Aurora Telecom**, **Exolve**, **Voximplant**, **MCN Telecom**, **Finenumbers**), with PSTN-based operator enrichment.

## Stack

- Backend: FastAPI, SQLAlchemy 2, Alembic, httpx, PostgreSQL
- Frontend: Next.js + TypeScript
- Compose: `db` + `backend` + `frontend`

## What it does

- Unified sync of free/purchased numbers (wipe-and-reload per `(provider, inventory_kind)` with safety guards)
- Normalized catalog UI (filters, infinite scroll, XLSX export)
- Local PSTN INN ranges cache used **only** to fill the **Оператор** column
- Daily schedule option at 00:00 Europe/Moscow (requires ready min cache)
- Separate «Номера DIDWW» section (`/didww`): international DIDWW coverage by DID Group, synced by its own button outside the RU run
- Separate «Номера Twilio» section (`/twilio`): sample of available E.164 numbers (not a full inventory), synced by «Загрузка регионов»

This is **not** a CDR / RADIUS / softswitch platform.

## Provider docs

Index: [`docs/providers/README.md`](docs/providers/README.md)

- SipOut: [`docs/providers/sipout/SOURCE.md`](docs/providers/sipout/SOURCE.md)
- Runexis: [`docs/providers/runexis/SOURCE.md`](docs/providers/runexis/SOURCE.md)
- UIS: [`docs/providers/uis/SOURCE.md`](docs/providers/uis/SOURCE.md)
- Aurora Telecom: [`docs/providers/aurora/SOURCE.md`](docs/providers/aurora/SOURCE.md)
- Exolve: [`docs/providers/exolve/SOURCE.md`](docs/providers/exolve/SOURCE.md)
- Voximplant: [`docs/providers/voximplant/SOURCE.md`](docs/providers/voximplant/SOURCE.md)
- MCN Telecom: [`docs/providers/mcn/SOURCE.md`](docs/providers/mcn/SOURCE.md)
- DIDWW: [`docs/providers/didww/SOURCE.md`](docs/providers/didww/SOURCE.md)
- Twilio: [`docs/providers/twilio/SOURCE.md`](docs/providers/twilio/SOURCE.md)
- Finenumbers/PSTN: [`docs/providers/finenumbers-contract.md`](docs/providers/finenumbers-contract.md)

**Locked product decisions:** provider APIs are read-only; wipe is per inventory slice (not full catalog purge); sync requires manually loaded min PSTN INN cache (СИПАУТНЭТ, ИНТЕРНОД, Фронтир Нетворк).

## Admin login

Set in `.env` (not committed):

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=...
ADMIN_SESSION_SECRET=...
```

UI: http://localhost:3000/login → session Bearer token for `/api/v1`.

## Local run (Docker)

```bash
cp .env.example .env
# edit ADMIN_USERNAME / ADMIN_PASSWORD
docker compose up --build
```

- API: http://localhost:8000/docs
- UI: http://localhost:3000

1. Sign in as admin
2. Configure provider credentials in **Настройки**
3. Load PSTN operator cache (**Загрузить кеш**)
4. Run sync on **Синхронизация**

## GHCR images (linux/amd64 only)

Published by GitHub Actions to:

- `ghcr.io/finenumbers/did-backend`
- `ghcr.io/finenumbers/did-frontend`

```bash
docker compose -f docker-compose.ghcr.yml --env-file .env up -d
```

No ARM / multi-arch builds.

## Portainer + Nginx Proxy Manager

Use the existing Docker network `proxy` (NPM). No host ports published.

- Stack file: [`docker-compose.portainer.yml`](docker-compose.portainer.yml)
- Env template: [`deploy/portainer.env.example`](deploy/portainer.env.example)
- Full guide: [`deploy/PORTAINER.md`](deploy/PORTAINER.md)

NPM forward: `did-frontend:3000` (UI). Optional API: `did-backend:8000`.

**Redeploy always uses `:latest`** (`DID_IMAGE_TAG=latest` + `pull_policy: always`). After CI publishes new images, update/recreate the Portainer stack (Re-pull image).

## Local run (without Compose frontend)

```bash
docker compose up -d db

cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .
export DATABASE_URL=postgresql+psycopg://did:did@localhost:5432/did
alembic upgrade head
uvicorn app.main:app --reload

cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

## Architecture

See [architecture.md](architecture.md) and [db_schema.md](db_schema.md).

# Deploy with Portainer + Nginx Proxy Manager (NPM)

Target layout: containers join the existing Docker network `proxy` used by NPM. No published host ports.

## 1. Prerequisites

On the Docker host:

```bash
# if NPM already uses a network named "proxy", skip create
docker network ls | grep -w proxy || docker network create proxy
```

Confirm NPM container is attached to that network (`PROXY_NETWORK_NAME` if renamed).

Host must pull **linux/amd64** images (GHCR builds are amd64-only).

## 2. Portainer stack

1. Portainer → **Stacks** → **Add stack**
2. Name: `did`
3. Web editor: paste [`docker-compose.portainer.yml`](../docker-compose.portainer.yml)
4. Environment variables: from [`portainer.env.example`](portainer.env.example) — set real passwords and `BACKEND_CORS_ORIGINS`
5. Deploy

Stable container DNS names for NPM:

| Service  | Hostname (Docker DNS) | Port |
|----------|------------------------|------|
| UI       | `did-frontend`         | 3000 |
| API      | `did-backend`          | 8000 |
| Postgres | `did-db` (internal only) | 5432 |

`did-db` is **not** on `proxy` — only on `did_internal`.

## 3. NPM Proxy Host (UI)

Typical single-host setup (recommended):

| Field | Value |
|-------|--------|
| Domain Names | `did.example.com` |
| Scheme | `http` |
| Forward Hostname / IP | `did-frontend` |
| Forward Port | `3000` |
| Websockets | on (optional, Next) |
| Block Common Exploits | on |
| SSL | Let's Encrypt as usual |

Browser calls `/api/backend/...` on the same host; Next.js proxies to `http://backend:8000` inside Docker.

Set stack env:

```env
BACKEND_CORS_ORIGINS=https://did.example.com
NEXT_PUBLIC_API_URL=/api/backend
BACKEND_INTERNAL_URL=http://backend:8000
```

**Auth:** keep a **single** `backend` replica for schedule/sync. Optional `ADMIN_API_TOKEN` belongs on the **backend** service only (scripts/CI call `did-backend` directly). Do **not** set it on `frontend` — the Next `/api/backend` proxy never injects a machine token (that would bypass login).

## 4. Optional: separate API host

Only if you need direct OpenAPI access (exposes `/docs` without the UI login gate — prefer internal-only):

| Field | Value |
|-------|--------|
| Domain | `did-api.example.com` |
| Forward Hostname / IP | `did-backend` |
| Forward Port | `8000` |

Then add that origin to `BACKEND_CORS_ORIGINS` if a browser talks to it cross-origin.

## 5. Login

Open `https://did.example.com/login` with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from the stack env.

## 6. Redeploy / upgrade (always latest)

Default is **`DID_IMAGE_TAG=latest`** with `pull_policy: always` on app services.

After a new image is published to GHCR (`:latest` is updated on every push to `main` and every release tag):

1. Portainer → Stack `did` → **Editor** → **Update the stack**
2. Enable **Re-pull image** / recreate if Portainer shows the option
3. Or: **Stop** → **Start** the stack so images are pulled again

Do **not** pin version tags for routine redeploys — keep `DID_IMAGE_TAG=latest`.

## 7. UIS Data API egress IP

UIS requires the server egress IP in the personal account API allowlist before sync/test work. Add the Docker host public IP (or `0.0.0.0/0` for lab) under UIS ЛК → API security. Credentials (`access_token`) are entered in Settings → UIS after deploy.

## 7b. Aurora Telecom CSV egress

Aurora free numbers load via plain **HTTP** to `bill.auroratelecom.ru:8080` (public regional CSVs, no auth): `Crimea.csv`, `Grozny.csv`, `MSK.csv`, `Sevastopol.csv`, `Simferopol.csv`, `SPb.csv` under `/bgbilling/numbers/`. The legacy `all_free.csv` is **not** fetched. The backend container must be allowed outbound HTTP to that host/port. No credentials in Settings — optional `base_url` is the directory prefix (a legacy single `.csv` URL is treated as its parent directory).

## 8. Sync dropped XLSX volume

Backend writes the latest unmapped/duplicate numbers report to `/data/sync/sync_dropped_latest.xlsx` (volume `did_sync_data`). Download from **Синхронизация** after a finished run. The file is overwritten on each new sync.

## 8b. Sync debug log

Backend writes a detailed sync debug log to `/data/sync/sync_latest.log` on the same volume. The file is **truncated at the start of every new sync** and flushed after each stage / progress line (partial download is valid while a sync is running). Download from **Синхронизация → Скачать лог**.

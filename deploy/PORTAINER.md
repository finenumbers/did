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

## 4. Optional: separate API host

Only if you need direct OpenAPI access:

| Field | Value |
|-------|--------|
| Domain | `did-api.example.com` |
| Forward Hostname / IP | `did-backend` |
| Forward Port | `8000` |

Then add that origin to `BACKEND_CORS_ORIGINS` if a browser talks to it cross-origin.

## 5. Login

Open `https://did.example.com/login` with `ADMIN_USERNAME` / `ADMIN_PASSWORD` from the stack env.

## 6. Upgrade

Change `DID_IMAGE_TAG` (e.g. `0.1.1` → `0.1.2`) and **Update the stack**, or set `latest` and recreate containers after GHCR publish.

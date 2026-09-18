# Deploying EchoTrace

The whole stack (backend, frontend, Postgres) is packaged as Docker Compose
services. This is what you run on your own host/VPS/cloud VM — nothing here
provisions cloud infrastructure or a domain for you; it makes the app ready
to point one at.

## 1. Local / first run (plain HTTP, no domain needed)

```bash
cp .env.example .env
# edit .env:
#   JWT_SECRET      — required. Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
#   ANTHROPIC_API_KEY — optional, only needed for the agentic /api/verdict endpoint
#   POSTGRES_PASSWORD — optional, defaults to "echotrace" if unset

docker compose up -d --build
```

- Frontend: `http://localhost:8080` (or whatever `FRONTEND_PORT` you set)
- Backend health check: `http://localhost:8080/api/health` (proxied) or
  directly at the backend container's `8010` if you expose it
- First run: register an account on the frontend, then log in.

The backend image is large (torch + transformers + the committed model
weights, ~2-3GB) — the first build takes a while. Subsequent builds are
fast (layer cache).

## 2. Putting a real domain in front of it (automatic HTTPS)

Point your domain's DNS A/AAAA record at the host, then:

```bash
# in .env:
DOMAIN=yourdomain.com

docker compose --profile domain up -d --build
```

This brings up an additional `caddy` service that terminates TLS
(automatic Let's Encrypt certificate, auto-renewed) and reverse-proxies to
the frontend container. Ports 80/443 must be free on the host and reachable
from the internet for the ACME HTTP challenge to succeed.

If you'd rather use your own reverse proxy / load balancer / managed TLS
(e.g. behind a cloud provider's load balancer) instead of the bundled
Caddy service, just don't use the `domain` profile — point your own proxy
at the `frontend` container's port (`FRONTEND_PORT`, default 8080) instead.

## 3. Environment variables reference

See `.env.example` for the full list with explanations. The load-bearing
ones:

| Variable | Required | Notes |
|---|---|---|
| `JWT_SECRET` | yes | Session signing secret. Backend refuses to start auth without it. |
| `ANTHROPIC_API_KEY` | no | Only needed for `/api/verdict` (the agentic verdict layer). |
| `POSTGRES_PASSWORD` | no | Defaults to `echotrace`. Set a real one for anything beyond local use. |
| `CORS_ORIGINS` | no | Only matters if something other than the bundled nginx-proxied frontend calls the API directly. |
| `DOMAIN` | no | Set to enable the `caddy` profile (automatic HTTPS). |

## 4. Data persistence

Postgres data lives in the `echotrace-db-data` named Docker volume — it
survives `docker compose down` (but not `docker compose down -v`). Back it
up with `docker exec` + `pg_dump`, or your usual volume backup approach,
before any destructive operation.

## 5. Live retrieval — network requirements

The backend needs outbound internet access to `api.gdeltproject.org` and to
whatever news publisher domains a search turns up — no API key needed for
GDELT itself, but a host with restrictive egress rules will need those
allowed. (This was not testable from the sandbox this project was built in,
which itself has restricted egress — see the retrieval module docstrings.
Verify with a real investigation on first deploy.)

## 6. Rebuilding after a code change

```bash
docker compose up -d --build
```

Compose only rebuilds images whose build context changed.

## 7. Logs / troubleshooting

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose ps
```

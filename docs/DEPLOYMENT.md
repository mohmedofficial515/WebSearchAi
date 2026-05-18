# 🚀 Deployment Guide

How to run WebSearchAi beyond your laptop.

> **Phase 1 limitation:** no authentication yet. Either keep it on localhost or front it with a reverse proxy + basic auth until Phase 8 ships.

---

## 🎯 Deployment targets

| Target | When to pick it | Effort |
|---|---|---|
| **Local laptop** | Personal use, demos, dev | 0 — already works |
| **Docker (single host)** | Self-hosting on a VPS / NAS | Low |
| **Docker Compose + Redis** | Multiple concurrent users, HA tasks | Medium |
| **Cloud Run / Fly.io** | Serverless, scale-to-zero | Medium |
| **Kubernetes** | Enterprise, > 10 concurrent agents | High |

---

## 🐳 Docker (single container)

The included `Dockerfile` builds a Playwright-ready image.

### Build & run

```bash
# Build
docker build -t websearchai:latest .

# Run
docker run -d \
  --name websearchai \
  -p 8000:8000 \
  -e MISTRAL_API_KEY=your_key \
  -e BROWSER_HEADLESS=true \
  -v $(pwd)/outputs:/app/outputs \
  websearchai:latest
```

The `outputs/` volume mount means screenshots, reports, and (Phase 2) memory.db persist across restarts.

### Resource requirements

| Workload | CPU | RAM | Disk |
|---|---|---|---|
| Idle | 0.1 core | 200 MB | 1.5 GB image + outputs |
| One active task | 1 core | 1 GB | + ~5 MB / task in `outputs/sessions` |
| 3 concurrent tasks | 2 cores | 3 GB | … |

Chromium is the dominant memory consumer — each browser context eats ~300–500 MB.

---

## 🐳 Docker Compose (with Redis, optional)

Useful when:
- You want a real task queue (replaces in-memory dict)
- You want metrics persistence (Phase 10)

```yaml
# docker-compose.yml — shipped in the repo
services:
  app:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    volumes: ["./outputs:/app/outputs"]
    depends_on: [redis]
  redis:
    image: redis:7-alpine
    volumes: ["redis-data:/data"]

volumes:
  redis-data:
```

```bash
docker compose up -d
docker compose logs -f app
```

---

## ☁️ Fly.io (recommended for small deployments)

Fly has good Playwright support and a generous free tier.

```bash
fly launch --no-deploy
# Edit fly.toml: vm_size = "shared-cpu-2x", memory_mb = 2048
fly secrets set MISTRAL_API_KEY=...
fly deploy
```

Persistent storage (Phase 2 memory):
```bash
fly volumes create websearchai_data --size 1
# Then mount it in fly.toml at /app/outputs
```

---

## ☁️ Cloud Run (GCP)

```bash
gcloud run deploy websearchai \
  --source . \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 600 \
  --set-env-vars MISTRAL_API_KEY=...,BROWSER_HEADLESS=true
```

**Caveats:**
- Cloud Run instances die after each request unless you use min-instances ≥ 1 → memory and profiles don't persist between cold starts. Mount Cloud Storage FUSE for `outputs/` if you need persistence.
- WebSocket support requires Cloud Run gen2 (default since 2024).

---

## 🛡️ Putting it behind a reverse proxy

Until Phase 8, lock down access with a proxy.

### Caddy (simplest)

```caddyfile
websearchai.yourdomain.com {
    basic_auth {
        admin $2a$14$...  # bcrypt hash
    }
    reverse_proxy localhost:8000
}
```

### Nginx (traditional)

```nginx
server {
    listen 443 ssl http2;
    server_name websearchai.yourdomain.com;

    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/htpasswd;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 600s;
    }
}
```

---

## 🔧 Production checklist

Before exposing to anyone other than yourself:

- [ ] `MISTRAL_API_KEY` is set via environment, not committed
- [ ] `BROWSER_HEADLESS=true`
- [ ] `LOG_LEVEL=INFO` (not DEBUG)
- [ ] Reverse proxy with TLS termination
- [ ] HTTP basic auth or VPN access only
- [ ] `outputs/` is on a persistent volume
- [ ] Resource limits set (don't let one runaway task OOM the host)
- [ ] Log rotation configured (Docker handles this; bare metal: logrotate)
- [ ] Backup `outputs/profiles/` and (Phase 2) `outputs/memory.db`
- [ ] Monitor disk usage — screenshots add up

---

## 📊 Observability (Phase 10 preview)

Coming in Phase 10, but if you want a head start:

| Signal | Tool |
|---|---|
| Logs | Docker log driver → Loki / Cloudwatch |
| Metrics | `/metrics` endpoint → Prometheus → Grafana |
| Traces | OpenTelemetry → Jaeger / Tempo |
| Errors | Sentry SDK in `src/api/main.py` |

The `docs/grafana/` folder will contain a starter dashboard once Phase 10 lands.

---

## 🆘 Troubleshooting deployments

### "Playwright executable not found"
You forgot `python -m playwright install chromium`. The provided Dockerfile does this automatically; if you built your own image, add that step.

### Browser crashes after ~10 tasks
Memory leak from accumulated contexts. Quick fix: restart the service every N tasks via a wrapper script. Real fix: Phase 6 will pool browsers properly.

### WebSocket disconnects after 60s
Reverse proxy timeout. Set `proxy_read_timeout 600s;` (nginx) or equivalent.

### Tasks succeed locally but fail in Docker
Almost always missing Playwright deps. Use the official `mcr.microsoft.com/playwright/python` base image (which the included Dockerfile does).

### LLM calls are 10× slower in production
Likely TLS handshake overhead on cold connections. The Mistral client reuses an `httpx.AsyncClient` — make sure you're not creating a new client per request.

---

## 🌱 Scaling beyond one host

When you outgrow a single container:

1. **Externalize the task queue** — Redis + `arq` or `dramatiq` (Phase 6 deliverable).
2. **Externalize the browser pool** — run Playwright workers on dedicated nodes; control plane stays small.
3. **Externalize memory** — Phase 2's SQLite moves to Postgres + pgvector for embeddings.
4. **Externalize artifacts** — `outputs/` becomes S3-compatible storage (MinIO, R2, S3).

Don't do any of this until you actually need it.

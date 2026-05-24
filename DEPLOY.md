# Deploying SteadyPlan

SteadyPlan runs as a Docker container. Your data stays on your machine — nothing is sent to the cloud.

Compatibility note: the Docker image is still published under the historical name `ghcr.io/jahumac/shelly-finance:latest` until a separate repo/package rename task.

## Network posture (recommended)
- Safe default: run SteadyPlan on your home LAN or VPN only. Do not port-forward it to the public internet.
- Optional public access: you can expose SteadyPlan like any other self-hosted web app (reverse proxy + HTTPS, or a tunnel/VPN approach). Because SteadyPlan contains sensitive financial data, treat public exposure as an advanced admin choice and configure it carefully (extra auth, strong passwords).
- If you expose it publicly: use HTTPS on a reverse proxy (e.g. Nginx Proxy Manager), enable production cookie settings, and add an extra auth layer (Authelia, OAuth proxy, basic auth, etc.). Examples are common patterns, not requirements.

---

## Option A — Docker (any machine)

### Step 1 — Pull the image

```bash
docker pull ghcr.io/jahumac/shelly-finance:latest
```

### Step 2 — Run the container

```bash
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /path/to/steadyplan-data:/app/data \
  ghcr.io/jahumac/shelly-finance:latest
```

Replace `/path/to/steadyplan-data` with wherever you want SteadyPlan to store its database. For example:
- **Mac/Linux:** `~/steadyplan-data`
- **Unraid (new installs):** `/mnt/user/appdata/steadyplan`

If you're upgrading an existing install, you can keep your current container name and data directory (for example `--name shelly`, `./data`, or `/mnt/user/appdata/shelly-finance`). No rename is required.

What each flag does:
- `-d` — runs in the background
- `--restart unless-stopped` — auto-starts on reboot
- `-p 8000:8000` — makes it accessible on port 8000 (change the left number if that port is taken, e.g. `-p 8001:8000`)
- `-v .../data:/app/data` — persists your database and secret key outside the container

### Step 3 — Open it

Go to **http://localhost:8000** (or replace `localhost` with your server's IP).

You'll see the setup screen the first time — create your account and you're in.

First run notes:

- SteadyPlan stores its database and secret key under the mounted `/app/data` volume (your host path from `-v ...:/app/data`).
- If you don't set any external price API keys, SteadyPlan still runs normally (manual balances/manual holdings values, and any Yahoo-backed lookups you use).

---

## Option B — Docker Compose

If you cloned this repo, you can use the included `docker-compose.yml`. Otherwise, create a minimal `docker-compose.yml`:

```yaml
services:
  steadyplan:
    image: ghcr.io/jahumac/shelly-finance:latest
    container_name: steadyplan
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    restart: unless-stopped
```

Then run:

```bash
docker compose up -d
```

---

## Option C — Unraid

### From Community Apps (recommended)

Search for **SteadyPlan** in the Unraid Community Apps store and click Install. If the listing hasn't been renamed yet, search for **Shelly Finance** (legacy) instead. For new installs, set the data path to `/mnt/user/appdata/steadyplan` and pick your port.

If you're upgrading an existing install, you can keep your current data directory (for example `/mnt/user/appdata/shelly-finance`). No rename is required.

### Manual install via SSH

```bash
ssh root@YOUR_UNRAID_IP
docker pull ghcr.io/jahumac/shelly-finance:latest
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /mnt/user/appdata/steadyplan:/app/data \
  ghcr.io/jahumac/shelly-finance:latest
```

Then open **http://YOUR_UNRAID_IP:8000** in your browser.

### Production security settings

For a local/home-network HTTP deployment, SteadyPlan keeps secure cookies disabled by default so login works at `http://YOUR_UNRAID_IP:8000`.

If you publish SteadyPlan behind HTTPS, set production mode so browser cookies are marked Secure:

```yaml
environment:
  - APP_ENV=production
```

Production mode defaults these to enabled:

```text
SESSION_COOKIE_SECURE=1
REMEMBER_COOKIE_SECURE=1
```

Only override them back to `0` if you deliberately run over plain HTTP. If SteadyPlan sits behind a trusted reverse proxy and you need client IP/protocol headers honoured, also set `TRUST_PROXY_HEADERS=1`; leave it unset for direct access.

### Rate-limit storage and workers

SteadyPlan defaults to one Gunicorn worker:

```text
WEB_CONCURRENCY=1
RATELIMIT_STORAGE_URI=memory://
```

That keeps the built-in login/API rate limits honest for a small self-hosted SQLite app. The `memory://` limiter is process-local; if you run multiple workers, each worker has its own limit bucket.

Only set `WEB_CONCURRENCY` above `1` if you also configure shared rate-limit storage, for example Redis:

```yaml
environment:
  - WEB_CONCURRENCY=2
  - RATELIMIT_STORAGE_URI=redis://redis:6379/0
```

If SteadyPlan sees `WEB_CONCURRENCY>1` with `RATELIMIT_STORAGE_URI=memory://`, it logs a startup warning.

---

## Updating

Pull the latest image and recreate the container:

```bash
docker pull ghcr.io/jahumac/shelly-finance:latest
docker stop steadyplan
docker rm steadyplan
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /path/to/steadyplan-data:/app/data \
  ghcr.io/jahumac/shelly-finance:latest
```

Or with Docker Compose:

```bash
docker compose pull
docker compose up -d
```

Your data is safe — it lives in the volume you mounted and is not touched by updates.

---

## Checking logs

```bash
docker logs steadyplan
# or follow live:
docker logs -f steadyplan
```

---

## Building from source

If you prefer to build the image yourself rather than using the pre-built one:

```bash
git clone https://github.com/Jahumac/shelly-finance.git
cd shelly-finance
docker build -t steadyplan .
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v ./data:/app/data \
  steadyplan
```

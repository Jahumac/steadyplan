# Deploying SteadyPlan

SteadyPlan runs as a Docker container. Your data stays on your machine — nothing is sent to the cloud.

Primary Docker image: `ghcr.io/jahumac/steadyplan:latest`

Legacy image (during transition): `ghcr.io/jahumac/shelly-finance:latest`

Existing installs do not need to rename their data directory. The safest migration is to run the new container image against the same `/app/data` mount first.

## Network posture (recommended)
- Safe default: run SteadyPlan on your home LAN or VPN only. Do not port-forward it to the public internet.
- Optional public access: you can expose SteadyPlan like any other self-hosted web app (reverse proxy + HTTPS, or a tunnel/VPN approach). Because SteadyPlan contains sensitive financial data, treat public exposure as an advanced admin choice and configure it carefully (extra auth, strong passwords).
- If you expose it publicly: use HTTPS on a reverse proxy (e.g. Nginx Proxy Manager), enable production cookie settings, and add an extra auth layer (Authelia, OAuth proxy, basic auth, etc.). Examples are common patterns, not requirements.

---

## Option A — Docker (any machine)

### Step 1 — Pull the image

```bash
docker pull ghcr.io/jahumac/steadyplan:latest
```

### Step 2 — Run the container

```bash
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /path/to/steadyplan-data:/app/data \
  ghcr.io/jahumac/steadyplan:latest
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
    image: ghcr.io/jahumac/steadyplan:latest
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

### Migrating from `shelly-finance` (single-user transition)

If your existing data folder is still named `/mnt/user/appdata/shelly-finance`, the safest migration is to keep that folder and simply run the new image against it first:

1) Stop the old container (whatever it is named), but do not delete your appdata folder.

2) Start the new container and map `/app/data` to the existing folder:

```bash
docker pull ghcr.io/jahumac/steadyplan:latest
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /mnt/user/appdata/shelly-finance:/app/data \
  ghcr.io/jahumac/steadyplan:latest
```

3) Verify your data in the UI. Only remove the old container once you’re confident.

Optional cleanup (later): copy `/mnt/user/appdata/shelly-finance` to `/mnt/user/appdata/steadyplan`, update the volume mapping, and keep the old folder as rollback until you’re sure.

### Manual install via SSH

```bash
ssh root@YOUR_UNRAID_IP
docker pull ghcr.io/jahumac/steadyplan:latest
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /mnt/user/appdata/steadyplan:/app/data \
  ghcr.io/jahumac/steadyplan:latest
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

Before upgrades or risky changes:
- Download a per-user JSON export from **Settings → Download JSON export** (portable, user-scoped).
- Back up the whole `/app/data` directory (whole instance: `finance.db`, `secret_key.txt`, and `backups/`).

Pull the latest image and recreate the container:

```bash
docker pull ghcr.io/jahumac/steadyplan:latest
docker stop steadyplan
docker rm steadyplan
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /path/to/steadyplan-data:/app/data \
  ghcr.io/jahumac/steadyplan:latest
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
git clone https://github.com/Jahumac/steadyplan.git
cd steadyplan
docker build -t steadyplan .
docker run -d \
  --name steadyplan \
  --restart unless-stopped \
  -p 8000:8000 \
  -v ./data:/app/data \
  steadyplan
```

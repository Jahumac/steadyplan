# Deploying Shelly

Shelly runs as a Docker container. Your data stays on your machine — nothing is sent to the cloud.

---

## Option A — Docker (any machine)

### Step 1 — Pull the image

```bash
docker pull ghcr.io/jahumac/shelly-finance:latest
```

### Step 2 — Run the container

```bash
docker run -d \
  --name shelly \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /path/to/shelly-data:/app/data \
  ghcr.io/jahumac/shelly-finance:latest
```

Replace `/path/to/shelly-data` with wherever you want Shelly to store its database. For example:
- **Mac/Linux:** `~/shelly-data`
- **Unraid:** `/mnt/user/appdata/shelly/data`

What each flag does:
- `-d` — runs in the background
- `--restart unless-stopped` — auto-starts on reboot
- `-p 8000:8000` — makes it accessible on port 8000 (change the left number if that port is taken, e.g. `-p 8001:8000`)
- `-v .../data:/app/data` — persists your database and secret key outside the container

### Step 3 — Open it

Go to **http://localhost:8000** (or replace `localhost` with your server's IP).

You'll see the setup screen the first time — create your account and you're in.

---

## Option B — Docker Compose

Create a `docker-compose.yml`:

```yaml
services:
  shelly:
    image: ghcr.io/jahumac/shelly-finance:latest
    container_name: shelly
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

Search for **Shelly** in the Unraid Community Apps store and click Install. Set the data path to `/mnt/user/appdata/shelly/data` and pick your port.

### Manual install via SSH

```bash
ssh root@YOUR_UNRAID_IP
docker pull ghcr.io/jahumac/shelly-finance:latest
docker run -d \
  --name shelly \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /mnt/user/appdata/shelly/data:/app/data \
  ghcr.io/jahumac/shelly-finance:latest
```

Then open **http://YOUR_UNRAID_IP:8000** in your browser.

### Production security settings

For a local/home-network HTTP deployment, Shelly keeps secure cookies disabled by default so login works at `http://YOUR_UNRAID_IP:8000`.

If you publish Shelly behind HTTPS, set production mode so browser cookies are marked Secure:

```yaml
environment:
  - APP_ENV=production
```

Production mode defaults these to enabled:

```text
SESSION_COOKIE_SECURE=1
REMEMBER_COOKIE_SECURE=1
```

Only override them back to `0` if you deliberately run over plain HTTP. If Shelly sits behind a trusted reverse proxy and you need client IP/protocol headers honoured, also set `TRUST_PROXY_HEADERS=1`; leave it unset for direct access.

### Rate-limit storage and workers

Shelly defaults to one Gunicorn worker:

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

If Shelly sees `WEB_CONCURRENCY>1` with `RATELIMIT_STORAGE_URI=memory://`, it logs a startup warning.

---

## Updating

Pull the latest image and recreate the container:

```bash
docker pull ghcr.io/jahumac/shelly-finance:latest
docker stop shelly
docker rm shelly
docker run -d \
  --name shelly \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /path/to/shelly-data:/app/data \
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
docker logs shelly
# or follow live:
docker logs -f shelly
```

---

## Building from source

If you prefer to build the image yourself rather than using the pre-built one:

```bash
git clone https://github.com/Jahumac/shelly-finance.git
cd shelly-finance
docker build -t shelly .
docker run -d \
  --name shelly \
  --restart unless-stopped \
  -p 8000:8000 \
  -v ./data:/app/data \
  shelly
```

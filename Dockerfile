FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt requirements.in .
RUN pip install --no-cache-dir -r requirements.txt && rm requirements.in

COPY . .

# Ensure the data directory exists for the SQLite DB and secret key
RUN mkdir -p /app/data

EXPOSE 8000

# Use a single gunicorn worker by default so the in-memory rate limiter is
# honest for the normal self-hosted Docker setup. Set WEB_CONCURRENCY>1 only
# together with shared rate-limit storage such as Redis.
#
# Forwarded header trust is locked to localhost by default at the server layer.
# If you deliberately run behind a trusted reverse proxy/tunnel and also enable
# TRUST_PROXY_HEADERS=1 in the app, widen FORWARDED_ALLOW_IPS explicitly.
CMD ["sh", "-c", "gunicorn --workers=${WEB_CONCURRENCY:-1} --bind=0.0.0.0:8000 --timeout=60 --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1,::1}\" 'app:create_app()'"]

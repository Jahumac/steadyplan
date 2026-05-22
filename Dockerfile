FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure the data directory exists for the SQLite DB and secret key
RUN mkdir -p /app/data

EXPOSE 8000

# Use a single gunicorn worker by default so the in-memory rate limiter is
# honest for the normal self-hosted Docker setup. Set WEB_CONCURRENCY>1 only
# together with shared rate-limit storage such as Redis.
CMD ["sh", "-c", "gunicorn --workers=${WEB_CONCURRENCY:-1} --bind=0.0.0.0:8000 --timeout=60 --forwarded-allow-ips=* 'app:create_app()'"]

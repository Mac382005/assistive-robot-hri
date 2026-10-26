FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway injects PORT. One worker is intentional: the app contains an
# in-process APScheduler and uses a single SQLite database/volume.
CMD ["sh", "-c", "exec gunicorn --worker-class gthread --workers 1 --threads 4 --timeout 120 --keep-alive 30 --access-logfile - --error-logfile - --bind 0.0.0.0:${PORT:-5000} wsgi:app"]

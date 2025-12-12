#!/bin/bash
set -e

# Wait for database to be healthy
echo "Waiting for database..."
until pg_isready -h db -U raterhub > /dev/null 2>&1; do
  sleep 1
done
echo "Database is ready."

# Run database migrations if needed
# You can hook Alembic or similar here in future

# Start the app
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips="*"

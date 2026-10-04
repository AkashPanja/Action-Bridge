#!/bin/sh
# All-in-one entrypoint: API and background worker in a SINGLE container.
# Used by docker-compose.synology.yml (SQLite mode). The image default CMD
# (API only) is unchanged, so split deployments are unaffected.
set -e

if [ "${RUN_WORKER:-true}" = "true" ]; then
  python -m app.worker &
fi

if [ "$DEBUG" = "true" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
else
  exec gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-1}" --timeout 120
fi

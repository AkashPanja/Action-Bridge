# Combined single image: API + worker + baked-in frontend (served by FastAPI).
# Build from the repo root:  docker build -t akashpanja/actionbridge:latest .
# Run the worker from the same image by overriding the command:
#   command: ["python", "-m", "app.worker"]

FROM node:20-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Bake the SPA into the image; app/main.py serves it when present.
COPY --from=frontend /fe/dist ./app/static

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -sf http://localhost:8000/health || exit 1

CMD ["sh", "-c", "if [ \"$DEBUG\" = \"true\" ]; then exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload; else exec gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-4} --timeout 120; fi"]

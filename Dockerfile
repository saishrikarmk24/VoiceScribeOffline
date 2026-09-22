# MedScribe Live - FastAPI backend image.
#
# Built from the repository root so `scripts/test_gemini.py` ships with the image
# and can be run inside the container. The frontend has its own image in
# frontend/Dockerfile (nginx, which also proxies /api and /ws to this service).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# curl is used by the compose healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-postgres.txt ./backend/
RUN pip install --upgrade pip && pip install -r backend/requirements-postgres.txt

COPY backend/app ./backend/app
COPY backend/alembic ./backend/alembic
COPY backend/alembic.ini ./backend/alembic.ini
COPY scripts ./scripts

RUN mkdir -p /app/backend/storage/audio

WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=25s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

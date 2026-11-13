# syntax=docker/dockerfile:1

# --- Stage 1: build the frontend ----------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: the app -----------------------------------------------------------
# One image: the Python backend, which also serves the built frontend.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, at pinned versions, so this layer is reused until they change.
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/pyproject.toml ./
COPY backend/src ./src
RUN pip install --no-deps .

COPY --from=frontend /build/dist /app/static

# Everything the app stores (database, PDFs, images) lives in /data: mount a volume there.
ENV LEVET_DATA_DIR=/data \
    LEVET_STATIC_DIR=/app/static
RUN useradd --system --uid 1000 --create-home levet \
    && mkdir /data \
    && chown levet:levet /data
USER levet
VOLUME /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# --proxy-headers lets the app see the original scheme behind a reverse proxy,
# so that the login cookie is marked Secure over HTTPS. Which proxies are
# trusted is set with FORWARDED_ALLOW_IPS (see docker-compose.yml).
CMD ["uvicorn", "levet.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

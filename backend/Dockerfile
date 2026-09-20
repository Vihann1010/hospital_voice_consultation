# Multi-stage build: wheels are compiled in a builder image so the runtime
# image carries no compilers and stays small.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# Runtime system packages only:
#   curl          container healthcheck
#   libgl1/libglib2.0-0  OpenCV runtime deps PaddleOCR needs to import cv2
#   poppler-utils rasterises scanned PDFs so they can be OCR'd
#   libpq5        PostgreSQL client library for psycopg2 (migrations)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl libgl1 libglib2.0-0 poppler-utils libpq5 tini \
        # Devanagari glyphs for prescription PDFs. Without these, Hindi
        # instructions print as black boxes.
        fonts-freefont-ttf fonts-indic \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY alembic.ini .
COPY alembic ./alembic
COPY scripts ./scripts
COPY app ./app

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/media/reports /data/media/prescriptions \
                /data/media/signatures \
    && chown -R appuser:appuser /data/media /app
USER appuser

# Pre-download the OCR models into the image so the first report upload in
# production doesn't stall on a cold model fetch (or fail outright on a
# host with no outbound internet).
RUN python -c "from app.investigations.extraction import _get_ocr_engine; _get_ocr_engine()"

EXPOSE 8000

# Liveness only — a slow database must not trigger a restart loop.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1

# tini reaps zombies and forwards SIGTERM, so the graceful-shutdown path in
# lifespan actually runs instead of the process being killed outright.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--timeout-graceful-shutdown", "20", \
     "--workers", "1"]

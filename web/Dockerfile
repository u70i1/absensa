FROM python:3.14-slim-bookworm AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.14-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PHOTOS_DIR=/app/photos
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libarchive13 libcairo2 ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 absensa
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY scripts ./scripts
RUN mkdir -p photos backups /run/absensa && chown absensa:absensa photos backups /run/absensa && chmod 700 backups
USER absensa
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

# PostgreSQL client tools live only in the dedicated worker image. Use matching
# Debian/PostgreSQL images, including the client library required by PG 18.
FROM postgres:18.4-bookworm AS postgres-client
FROM runtime AS backup
USER root
RUN apt-get update && apt-get install -y --no-install-recommends liblz4-1 libzstd1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=postgres-client /usr/lib/postgresql/18/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=postgres-client /usr/lib/postgresql/18/bin/pg_restore /usr/local/bin/pg_restore
COPY --from=postgres-client /usr/lib/x86_64-linux-gnu/libpq.so.5.18 /usr/local/lib/libpq.so.5.18
RUN ln -s libpq.so.5.18 /usr/local/lib/libpq.so.5 && ldconfig && pg_dump --version && pg_restore --version
USER absensa
CMD ["python", "-m", "app.jobs.backups"]

FROM runtime AS web

# One image per Python service (gateway, recorder; later engine, rules), built from the repo root:
#   docker build -f infra/docker/python-service.Dockerfile --build-arg SERVICE=gateway .
# Code and locked dependencies only. Secrets come from the env file on the host, footage lives on a volume (D-30).
FROM python:3.11-slim-bookworm

# ffmpeg: the recorder's HLS/sprites and the gateway's replay cuts (libx264; docs/licenses.md)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv

WORKDIR /app
ARG SERVICE
COPY packages/py-trophy packages/py-trophy
COPY services/${SERVICE} services/${SERVICE}
RUN uv sync --frozen --no-dev --project services/${SERVICE} \
    && useradd --uid 1000 --create-home trophy

ENV PATH=/app/services/${SERVICE}/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    TROPHY_DATA_DIR=/data/local
USER trophy

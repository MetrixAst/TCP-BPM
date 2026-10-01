FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libreoffice-nogui \
    fonts-dejavu-core \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

ARG ENV_FILE=.env.production
ENV APP_ENV_FILE=${ENV_FILE}
COPY ${ENV_FILE} ${ENV_FILE}

COPY app ./app
COPY alembic.ini .
COPY alembic_ddl_utils.py .
COPY alembic ./alembic
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

RUN mkdir -p /app/downloads

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]

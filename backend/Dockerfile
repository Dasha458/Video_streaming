FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_PROJECT_ENVIRONMENT="/opt/venv" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app"

RUN uv venv /opt/venv

COPY pyproject.toml uv.lock ./

RUN uv sync --no-dev --frozen

# Migration tooling — not part of the main runtime deps but needed on boot
# so the container can auto-apply alembic migrations against PostgreSQL.
# Installed as a separate layer to avoid bloating the locked dependency tree.
RUN uv pip install --python /opt/venv/bin/python \
        "alembic>=1.16.5" \
        "psycopg2-binary>=2.9.11"

COPY src ./src
COPY app ./app
COPY main.py .
COPY log_conf.yaml .
COPY alembic.ini .
COPY alembic ./alembic
COPY utils ./utils
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN addgroup --system app && adduser --system --group --home /app app
RUN chown -R app:app /app /opt/venv
USER app

ENTRYPOINT ["/entrypoint.sh"]
CMD ["--host", "0.0.0.0", \
    "--port", "8000", \
    "--loop", "uvloop", \
    "--http", "httptools", \
    "--log-config", "log_conf.yaml"]

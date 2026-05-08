#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────
# Container entrypoint: run DB migrations, then start the FastAPI server.
#
# Migrations are retried because on a cold start the BFF may come up before
# Vault is unsealed or before PostgreSQL accepts connections — both cases
# make `alembic upgrade head` fail.  We retry for up to ~60 seconds and then
# hand off to uvicorn regardless.  If the DB is genuinely unreachable
# uvicorn will fail shortly after for the same reason and Docker will
# restart the container.
# ──────────────────────────────────────────────────────────────────────────
set -e

MAX_RETRIES="${MIGRATION_RETRIES:-30}"
RETRY_DELAY="${MIGRATION_RETRY_DELAY:-2}"

echo "[entrypoint] running alembic upgrade head …"
i=1
while [ "$i" -le "$MAX_RETRIES" ]; do
    if alembic upgrade head; then
        echo "[entrypoint] migrations applied successfully."
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "[entrypoint] WARNING: migrations failed after ${MAX_RETRIES} attempts — continuing startup." >&2
        break
    fi
    echo "[entrypoint] migration attempt ${i}/${MAX_RETRIES} failed, retrying in ${RETRY_DELAY}s …"
    i=$((i + 1))
    sleep "$RETRY_DELAY"
done

echo "[entrypoint] starting uvicorn …"
exec uvicorn main:app "$@"

#!/bin/sh
# Grafana's secrets come from Vault, like every other secret in this
# project. Grafana itself cannot read Vault -- that is an Enterprise
# feature -- so this runs first and hands them over as files.
#
# Files rather than environment variables on purpose: an environment
# variable is visible to anything that can run `docker inspect` or read
# /proc, and it ends up in `docker compose config` output. A file can be
# mode 400 and owned by the one user that needs it.
#
# Three jobs, all idempotent, all repeated on every start:
#   1. write Grafana's admin password and database password as files;
#   2. make the read-only database login match the password it was just
#      handed, so the two cannot drift;
#   3. write the Telegram contact point, if a bot token is stored.
set -eu

SECRETS_DIR=/secrets
ALERTING_DIR=/alerting
GRAFANA_UID=472

log() { echo "[grafana-bootstrap] $*"; }
die() { echo "[grafana-bootstrap] ERROR: $*" >&2; exit 1; }

[ -n "${VAULT_ADDR:-}" ] || die "VAULT_ADDR is not set"
# The configured address ends in a slash, which would make the request
# path //v1/... -- and Vault answers that with something that is not
# JSON, so the first sign of it is a parse error from jq.
VAULT_ADDR=$(printf '%s' "$VAULT_ADDR" | sed 's#/*$##')
[ -n "${VAULT_TOKEN:-}" ] || die "VAULT_TOKEN is not set"

# ── 1. Read ───────────────────────────────────────────────────────────
log "reading secret/grafana from Vault…"
response=$(curl -sS --fail-with-body --max-time 10 \
    -H "X-Vault-Token: ${VAULT_TOKEN}" \
    "${VAULT_ADDR}/v1/secret/data/grafana") || die \
    "Vault refused the request. Is it unsealed, and does secret/grafana exist?
    Create it with:
      docker exec vault vault kv put secret/grafana \\
        ADMIN_PASSWORD=<strong password> DB_PASSWORD=<strong password>"

printf '%s' "$response" | jq -e . >/dev/null 2>&1 ||
    die "Vault did not answer with JSON: $(printf '%s' "$response" | head -c 200)"

field() { printf '%s' "$response" | jq -r --arg k "$1" '.data.data[$k] // empty'; }

ADMIN_PASSWORD=$(field ADMIN_PASSWORD)
DB_PASSWORD=$(field DB_PASSWORD)
TELEGRAM_BOT_TOKEN=$(field TELEGRAM_BOT_TOKEN)
TELEGRAM_CHAT_ID=$(field TELEGRAM_CHAT_ID)

[ -n "$ADMIN_PASSWORD" ] || die "secret/grafana has no ADMIN_PASSWORD"
[ -n "$DB_PASSWORD" ] || die "secret/grafana has no DB_PASSWORD"

# Refusing the default outright: a password that is already public is not
# a password, and Grafana is reachable on the gateway in the dev profile.
[ "$ADMIN_PASSWORD" != "admin" ] || die \
    "ADMIN_PASSWORD is still 'admin'. Set a real one in Vault."

# ── 2. Hand them over as files ────────────────────────────────────────
mkdir -p "$SECRETS_DIR"
umask 077
printf '%s' "$ADMIN_PASSWORD" > "$SECRETS_DIR/admin_password"
printf '%s' "$DB_PASSWORD" > "$SECRETS_DIR/db_password"
chown "$GRAFANA_UID":0 "$SECRETS_DIR"/admin_password "$SECRETS_DIR"/db_password
chmod 400 "$SECRETS_DIR"/admin_password "$SECRETS_DIR"/db_password
log "wrote 2 secret files for uid $GRAFANA_UID"

# ── 3. Keep the database login in step ────────────────────────────────
# The role used to be created by the Postgres init script from a value in
# .env, which meant it existed only on a volume that had been created
# fresh, and the password lived in two places that could drift. Vault is
# the single source now, and this runs on every start, so an existing
# database is corrected rather than documented as a manual step.
log "syncing the grafana_ro login on ${POSTGRES_DB}…"
PGPASSWORD="$POSTGRES_PASSWORD" psql -v ON_ERROR_STOP=1 --quiet \
    -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -v pw="$DB_PASSWORD" <<'SQL'
SELECT format(
    CASE WHEN EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro')
         THEN 'ALTER ROLE grafana_ro LOGIN PASSWORD %L'
         ELSE 'CREATE ROLE grafana_ro LOGIN PASSWORD %L'
    END, :'pw') \gexec

GRANT CONNECT ON DATABASE :"DBNAME" TO grafana_ro;
GRANT USAGE ON SCHEMA public TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;

-- Tables a later migration adds must be readable too, without anyone
-- remembering to come back here.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;

-- SELECT and nothing else. Said explicitly because a role that quietly
-- gained write access would be invisible until it was used.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM grafana_ro;
REVOKE CREATE ON SCHEMA public FROM grafana_ro;
SQL
log "grafana_ro is in step with Vault"

# ── 4. Telegram, if it is configured ──────────────────────────────────
mkdir -p "$ALERTING_DIR"
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
    # Written here rather than committed because the file carries the bot
    # token. Grafana encrypts it into its own database on load.
    cat > "$ALERTING_DIR/telegram.yaml" <<YAML
# Generated at start from secret/grafana in Vault. Do not edit: it is
# rewritten on every boot, and it contains a bot token.
apiVersion: 1

contactPoints:
  - orgId: 1
    name: telegram
    receivers:
      - uid: telegram-main
        type: telegram
        settings:
          bottoken: "${TELEGRAM_BOT_TOKEN}"
          chatid: "${TELEGRAM_CHAT_ID}"
          message: |-
            {{ len .Alerts.Firing }} firing, {{ len .Alerts.Resolved }} resolved
            {{ range .Alerts.Firing }}
            {{ .Annotations.summary }}
            {{ .Annotations.description }}
            {{ end }}
          disable_notification: false
        disableResolveMessage: false

policies:
  - orgId: 1
    receiver: telegram
    group_by: ["alertname"]
    # One message per alert per five minutes at worst. An alerting channel
    # that repeats itself every thirty seconds gets muted, and then it is
    # worth nothing.
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 4h
YAML
    chown "$GRAFANA_UID":0 "$ALERTING_DIR/telegram.yaml"
    chmod 400 "$ALERTING_DIR/telegram.yaml"
    log "Telegram contact point written (chat ${TELEGRAM_CHAT_ID})"
else
    # Removed rather than left stale, so clearing the secret in Vault
    # actually turns delivery off.
    rm -f "$ALERTING_DIR/telegram.yaml"
    log "no TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in Vault -- alerts will be"
    log "visible in Grafana but delivered nowhere"
fi

log "done"

#!/bin/sh
# Grafana applies GF_SECURITY_ADMIN_PASSWORD only when it creates the
# admin user, which happens once, on an empty grafana_data volume. On
# every later start the stored password wins -- so an installation that
# was ever created with admin/admin keeps admin/admin no matter what
# Vault says, and the whole point of moving the secret out of the
# compose file is lost.
#
# Resetting it here makes Vault the source of truth on every boot. The
# reset writes straight to Grafana's own database before the server
# starts, so there is no window where both passwords work.
set -eu

PASSWORD_FILE=/run/secrets/grafana/admin_password

if [ -s "$PASSWORD_FILE" ]; then
    if grafana cli --homepath=/usr/share/grafana admin reset-admin-password \
            "$(cat "$PASSWORD_FILE")" >/dev/null 2>&1; then
        echo "[grafana-entrypoint] admin password set from Vault"
    else
        # Expected exactly once: on a fresh volume there is no admin user
        # yet, and Grafana is about to create it from
        # GF_SECURITY_ADMIN_PASSWORD__FILE -- the same value.
        echo "[grafana-entrypoint] no admin user yet; Grafana will create it from the same file"
    fi
else
    echo "[grafana-entrypoint] WARNING: $PASSWORD_FILE is missing or empty;" \
         "did grafana-bootstrap run?" >&2
fi

exec /run.sh "$@"

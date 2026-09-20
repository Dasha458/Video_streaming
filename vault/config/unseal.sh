#!/bin/sh
# Runs next to `vault server` at container start. Unseals an initialised
# vault from the two unseal keys in the environment; on a brand-new volume
# it just explains what to do and exits 0 so the server stays up for
# `vault operator init` (see README, "Ініціалізація Vault").
echo "[vault-unseal] waiting for vault to respond..."
until vault status >/dev/null 2>&1 || vault status 2>&1 | grep -q "Sealed"; do
  sleep 1
done

if vault status 2>&1 | grep -q "^Initialized *false"; then
  echo "[vault-unseal] vault is NOT initialised -- run: docker exec vault vault operator init -key-shares=2 -key-threshold=2"
  exit 0
fi

if vault status 2>&1 | grep -q "^Sealed *true"; then
  if [ -z "$VAULT_UNSEAL_KEY_1" ] || [ -z "$VAULT_UNSEAL_KEY_2" ]; then
    echo "[vault-unseal] vault is sealed but VAULT_UNSEAL_KEY_1/2 are empty -- fill Docker/.env and restart"
    exit 0
  fi
  echo "[vault-unseal] vault is sealed, unsealing..."
  vault operator unseal "$VAULT_UNSEAL_KEY_1" >/dev/null && \
  vault operator unseal "$VAULT_UNSEAL_KEY_2" >/dev/null && \
  echo "[vault-unseal] vault unsealed successfully" || \
  echo "[vault-unseal] unseal FAILED -- keys in Docker/.env do not match this vault's data"
else
  echo "[vault-unseal] vault is already unsealed"
fi

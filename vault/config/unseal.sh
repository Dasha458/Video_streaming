#!/bin/sh
echo "[vault-unseal] waiting for vault to respond..."
until vault status 2>&1 | grep -q "Initialized"; do
  sleep 1
done

if vault status 2>&1 | grep -q "Sealed.*true"; then
  echo "[vault-unseal] vault is sealed, unsealing..."
  vault operator unseal "$VAULT_UNSEAL_KEY_1"
  vault operator unseal "$VAULT_UNSEAL_KEY_2"
  echo "[vault-unseal] vault unsealed successfully"
else
  echo "[vault-unseal] vault is already unsealed"
fi

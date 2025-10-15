#!/usr/bin/env python3
from google.cloud import secretmanager
import os

OUTPUT_PATH = "/etc/tmkms/priv_validator_key.json"

client = secretmanager.SecretManagerServiceClient()

secret_name = "projects/508864053449/secrets/tmkms_jackal-testnet_priv_validator_key/versions/latest"

response = client.access_secret_version(request={"name": secret_name})
secret_data = response.payload.data.decode("utf-8")

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

with open(OUTPUT_PATH, "w") as f:
    f.write(secret_data)

os.chmod(OUTPUT_PATH, 0o600)

print(f"TMKMS INIT DONE: {OUTPUT_PATH}")
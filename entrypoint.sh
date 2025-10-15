#!/usr/bin/env bash

# Init TMKMS folder
if [ ! -d /opt/tmkms/secrets ]; then
  mkdir -p /tmp/tmkms && rm -rf /tmp/tmkms/*
  tmkms init /tmp/tmkms
  rm -f /tmp/tmkms/tmkms.toml
  mkdir -p /opt/tmkms
  cp -rf /tmp/tmkms/* /opt/tmkms/
fi

# Import key
python3 /import.py
tmkms softsign import /etc/tmkms/priv_validator_key.json /opt/tmkms/secrets/consensus.key
shred /etc/tmkms/priv_validator_key.json

tmkms start -c /opt/tmkms/tmkms.toml

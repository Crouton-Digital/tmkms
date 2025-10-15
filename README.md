# tmkms


tmkms init /opt/tmkms
tmkms softsign import /etc/tmkms/priv_validator_key.json /opt/tmkms/secrets/consensus.key
shred /opt/tmkms/secrets/consensus.key

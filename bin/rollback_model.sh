#!/usr/bin/env bash
set -euo pipefail
cd /root/pro_botti/models/registry
prev=$(ls -1t | sed -n '2p')
[ -n "$prev" ] || { echo "no previous model"; exit 1; }
ln -sfn "/root/pro_botti/models/registry/$prev" /root/pro_botti/models/current.joblib
systemctl restart pro-bot-15m

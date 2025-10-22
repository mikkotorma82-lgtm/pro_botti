#!/bin/bash
set -e
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Yritetään korjata mahdollinen avainformaatti
if grep -q "BEGIN RSA PRIVATE KEY" ~/.ssh/id_rsa; then
  echo "Avain vanhassa RSA-muodossa, muunnetaan..."
  ssh-keygen -p -m PEM -f ~/.ssh/id_rsa -N ""
fi

chmod 600 ~/.ssh/id_rsa
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa
ssh -T git@github.com || true

#!/usr/bin/env bash

set -eux

old_deploy_dir="$1"

if ! [[ -d "$old_deploy_dir" ]]; then
  echo "fatal: $old_deploy_dir does not exist or is not a directory"
  exit 1
fi

echo "==> switching symlink to $old_deploy_dir"
ln -sfn "$old_deploy_dir" /var/iafisher/deployments/current

# TODO: rollback database migrations?

systemctl --user daemon-reload
systemctl --user enable iafisher-site
systemctl --user restart iafisher-site
sudo systemctl restart caddy

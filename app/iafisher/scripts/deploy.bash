#!/usr/bin/env bash

set -eux

exec 200>/var/iafisher/deploy.lock
flock -n 200 || { echo "FATAL: deploy already in progress"; exit 1; }

archive_filepath="$1"
deploy_dir="/var/iafisher/deployments"
previous_deploy_filepath="$(readlink "$deploy_dir/current")"

echo "==> preparing to deploy"
echo "new deployment: $archive_filepath"
echo "old deployment: $previous_deploy_filepath"

cd "$deploy_dir"

echo "==> unzipping tarball"
archive_filename="$(basename "$archive_filepath")"
now="$(date -u +%Y%m%d-%H%M%S)"
archive_dir="$deploy_dir/${archive_filename%.tar.gz}-$now"
mkdir -p "$archive_dir"
mkdir "$archive_dir/code"
tar -xzf "$archive_filepath" -C "$archive_dir/code"
rm "$archive_filepath"

echo "==> installing python dependencies"
# temporarily disable `set -x` so the shell doesn't print the individual lines of `env-for-sourcing`
# which include secrets
set +x
source /var/iafisher/env-for-sourcing
set -x
cd "$archive_dir/code"
python3.11 -m venv .venv
source .venv/bin/activate
uv pip sync requirements.txt

echo "==> collecting static files"
./manage.py collectstatic --clear --noinput
# `staticfiles` is the value of `STATIC_ROOT` from the Django settings
sudo semanage fcontext -a -t httpd_sys_content_t "$archive_dir/code/staticfiles(/.*)?"
sudo restorecon -R -v "$archive_dir/code/staticfiles"
# make sure staticfiles point to current deploy (no-op after first deploy)
ln -sfn "$deploy_dir/current/code/staticfiles" /var/www/iafisher/static

echo "==> updating caddyfile"
sudo semanage fcontext -a -t httpd_config_t "$archive_dir/code/infra/caddyfile"
sudo restorecon "$archive_dir/code/infra/caddyfile"
# make sure caddyfile points to current deploy (no-op after first deploy)
sudo ln -sfn "$deploy_dir/current/code/infra/caddyfile" /etc/caddy/Caddyfile

echo "==> updating fail2ban"
sudo semanage fcontext -a -t etc_t "$archive_dir/code/infra/fail2ban/jail.local"
sudo restorecon "$archive_dir/code/infra/fail2ban/jail.local"
# make sure fail2ban points to current deploy (no-op after first deploy)
sudo ln -sfn "$deploy_dir/current/code/infra/fail2ban/jail.local" /etc/fail2ban/jail.local

echo "==> applying database migrations"
./manage.py migrate

echo "==> switching current symlink"
ln -sfn "$archive_dir" "$deploy_dir/current"

echo "==> restarting systemd service"
# make sure systemd service file points to current deploy (no-op after first deploy)
ln -sfn "$deploy_dir/current/code/infra/iafisher-site.service" ~/.config/systemd/user/iafisher-site.service

restart_everything() {
  systemctl --user daemon-reload
  systemctl --user enable iafisher-site
  systemctl --user restart iafisher-site
  sudo systemctl restart caddy fail2ban
}

restart_everything

sleep 2
echo "==> running health check"
if ! curl -sf -o /dev/null http://localhost:8080/health; then
  echo
  echo "FATAL: health check failed, reverting to old deploy"
  echo
  ln -sfn "$previous_deploy_filepath" "$deploy_dir/current"
  restart_everything
  exit 1
else
  echo "health check succeeded"
fi

old_deploys="$(ls -dt /var/iafisher/deployments/iafisher-* | tail -n +6)"
if [[ -n "$old_deploys" ]]; then
  echo "==> removing old deployments"
  echo $old_deploys | xargs --verbose rm -rf
fi

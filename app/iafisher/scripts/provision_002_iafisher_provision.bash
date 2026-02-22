#!/usr/bin/env bash

set -eux

echo "==> creating directories"
sudo mkdir -p /var/iafisher/{deployments,uploads}
sudo mkdir -p /var/fast-concordance
sudo chown -R iafisher:iafisher /var/iafisher /var/fast-concordance
sudo chmod -R 755 /var/iafisher /var/fast-concordance

echo "==> updating software"
# Without `dnf clean all` I sometimes see, e.g.:
#
# [Errno 2] No such file or directory: '/var/cache/dnf/baseos-522ed8e2b2f761ff/packages/ca-certificates-2025.2.80_v9.0.305-91.el9.noarch.rpm'
#
sudo dnf clean all
# If you don't do this, as of Jan 2026 there is a nasty bug where installing Postgres causes
# an OpenSSL version incompatibility that breaks SSH and bricks the server.
sudo dnf update -y

echo "==> configuring ssh"
sshd_config=/etc/ssh/sshd_config
sudo sed -i 's/^\(# \|\)PermitRootLogin [a-z-]\+$/PermitRootLogin no/' "$sshd_config"
sudo sed -i 's/^\(# \|\)PasswordAuthentication [a-z-]\+$/PasswordAuthentication no/' "$sshd_config"

if ! sudo grep '^PermitRootLogin no$' "$sshd_config" &> /dev/null; then
  echo "fatal: failed to set PermitRootLogin in $sshd_config"
  exit 1
fi

if ! sudo grep '^PasswordAuthentication no$' "$sshd_config" &> /dev/null; then
  echo "fatal: failed to set PasswordAuthentication in $sshd_config"
  exit 1
fi

sudo sshd -t
sudo systemctl restart sshd

echo "==> setting up firewall"
sudo dnf install -y firewalld
sudo systemctl enable firewalld
sudo systemctl start firewalld

sudo firewall-cmd --set-default-zone=drop
sudo firewall-cmd --permanent --zone=drop --add-service=ssh
sudo firewall-cmd --permanent --zone=drop --add-service=http
sudo firewall-cmd --permanent --zone=drop --add-service=https
sudo firewall-cmd --reload

echo "==> installing fail2ban"
# need "Extra Packages for Enterprise Linux" to get fail2ban
sudo dnf install -y epel-release
sudo dnf install -y fail2ban
sudo systemctl enable fail2ban

echo "==> installing python and tools"
sudo dnf install -y python3.11
curl -LsSf https://astral.sh/uv/install.sh | sh

echo "==> installing caddy"
sudo dnf install -y yum-utils
sudo dnf copr enable -y @caddy/caddy
sudo dnf install -y caddy

sudo mkdir -p /var/www/iafisher
sudo chown -R iafisher:iafisher /var/www/iafisher

sudo systemctl enable caddy

echo "==> installing postgres"
# https://www.postgresql.org/download/linux/redhat/
sudo dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-$(rpm -E %{rhel})-x86_64/pgdg-redhat-repo-latest.noarch.rpm
sudo dnf -qy module disable postgresql
sudo dnf install -y postgresql17-server postgresql17-contrib
sudo /usr/pgsql-17/bin/postgresql-17-setup initdb
sudo systemctl enable postgresql-17
sudo systemctl start postgresql-17

# systemd expects environment file in form `KEY=VALUE`, but for `source` to work it needs
# to be `export KEY=VALUE`. So we just have two copies.
envfile="/var/iafisher/env-for-systemd"
pgpassword=$(openssl rand -base64 32)
cat > "$envfile" <<EOF
IAFISHER_COM_ENV=prod
IAFISHER_COM_POSTGRES_PASSWORD=$pgpassword
EOF
sed 's/^/export /' "$envfile" > "/var/iafisher/env-for-sourcing"

sudo -u postgres psql <<EOF
CREATE DATABASE iafisher;
CREATE USER iafisher WITH PASSWORD '$pgpassword';
GRANT ALL PRIVILEGES ON DATABASE iafisher TO iafisher;
\c iafisher
GRANT ALL ON SCHEMA public TO iafisher;
\q
EOF

echo "==> setting up systemd user services"
mkdir -p ~/.config/systemd/user
loginctl enable-linger $USER
systemctl --user daemon-reexec

echo "==> installing development utilites"
sudo dnf install -y git lsof vim wget
wget 'https://iafisher.com/bootstrap.sh'
# TODO(2026-01): On a fresh Rocky Linux 9 instance from Digital Ocean, this fails with
#
#   /etc/bashrc: line 12: BASHRCSOURCED: unbound variable
#
bash bootstrap.sh $HOME || true

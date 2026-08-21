#!/usr/bin/env bash
# Standard EC2 shell user-data. Do not put NASA, GitHub, AWS or database secrets here.
set -Eeuo pipefail

exec > >(tee -a /var/log/nasa-etl-bootstrap.log) 2>&1

APP_USER="nasaetl"
APP_GROUP="nasaetl"
APP_UID="10001"
APP_GID="10001"
APP_DIR="/opt/nasa-etl"
APP_REPOSITORY_URL="https://github.com/Leoboas/nasaProject.git"
# Prefer a release tag or commit SHA. Terraform replaces this value from repository_ref.
APP_REF="main"

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  git \
  gnupg \
  nodejs \
  npm \
  python3 \
  python3-pip \
  python3-venv

# Docker Engine + Compose plugin from the official Docker APT repository.
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y --no-install-recommends \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
systemctl enable --now docker

if ! getent group "$APP_GROUP" >/dev/null; then
  groupadd --gid "$APP_GID" "$APP_GROUP"
fi
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd \
    --uid "$APP_UID" \
    --gid "$APP_GROUP" \
    --create-home \
    --shell /usr/sbin/nologin \
    "$APP_USER"
fi

# Containers write only their data directory. Docker is invoked by a root-owned
# systemd unit, so the application user never needs privileged docker-group access.
install -d -m 0750 -o "$APP_USER" -g "$APP_GROUP" /var/lib/nasa-etl
install -d -m 0750 -o "$APP_USER" -g "$APP_GROUP" /var/lib/nasa-etl/data
install -d -m 0700 -o root -g root /var/lib/nasa-etl/docker-config
install -d -m 0700 -o root -g root /etc/nasa-etl

# Bound the system journal in addition to per-container Docker log rotation.
install -d -m 0755 /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/nasa-etl.conf <<'EOF'
[Journal]
SystemMaxUse=200M
SystemMaxFileSize=25M
EOF
systemctl restart systemd-journald

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$APP_REPOSITORY_URL" "$APP_DIR"
fi
git -C "$APP_DIR" fetch --tags --force origin
git -C "$APP_DIR" checkout --detach "$APP_REF"
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"

# Build the job image without needing an environment file during bootstrap.
docker build --tag nasa-etl-runtime:local --file "$APP_DIR/Dockerfile.runtime" "$APP_DIR"

install -m 0644 "$APP_DIR/deploy/systemd/nasa-etl-postgres.service" /etc/systemd/system/nasa-etl-postgres.service
install -m 0644 "$APP_DIR/deploy/systemd/nasa-etl.service" /etc/systemd/system/nasa-etl.service
install -m 0644 "$APP_DIR/deploy/systemd/nasa-etl.timer" /etc/systemd/system/nasa-etl.timer
systemctl daemon-reload
systemctl enable nasa-etl.timer

echo "Bootstrap concluido. Crie /etc/nasa-etl/nasa-etl.env e inicie nasa-etl.service."

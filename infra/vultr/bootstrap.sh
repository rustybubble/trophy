#!/usr/bin/env bash
# First-boot setup of the Trophy GPU box (Vultr Cloud GPU, Ubuntu 22.04/24.04, NVIDIA driver from Vultr's image).
# Run once as root over SSH:  curl -fsSL <raw url> | bash   or   scp infra/vultr/bootstrap.sh root@BOX: && ssh root@BOX bash bootstrap.sh
# Idempotent. Installs Docker + the NVIDIA container toolkit, turns on the firewall (22, 80, 443 only), key-only SSH,
# and creates the host paths compose expects. It never writes secrets: copy the env files in yourself (README).
set -euo pipefail

need_nvidia() { command -v nvidia-smi >/dev/null && nvidia-smi -L; }
echo "== GPU"; need_nvidia || { echo "no NVIDIA driver: pick Vultr's GPU image or install the driver first"; exit 1; }

echo "== Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

echo "== NVIDIA container toolkit"
if ! command -v nvidia-ctk >/dev/null; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update && apt-get install -y nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
fi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L

echo "== Firewall: TCP 22, 80, 443 only (add UDP only if WebRTC ingest is turned on)"
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
# Docker publishes ports through iptables ahead of ufw, so only Caddy publishes any (docker-compose.yml).

echo "== SSH: keys only"
if [ -s /root/.ssh/authorized_keys ]; then
  sed -i -E 's/^#?PasswordAuthentication .*/PasswordAuthentication no/; s/^#?KbdInteractiveAuthentication .*/KbdInteractiveAuthentication no/' /etc/ssh/sshd_config
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin prohibit-password\n' > /etc/ssh/sshd_config.d/10-trophy.conf
  systemctl reload ssh || systemctl reload sshd
else
  echo "no /root/.ssh/authorized_keys: add your key before disabling passwords"; exit 1
fi

echo "== Host paths"
install -d -m 700 /etc/trophy
install -d -o 1000 -g 1000 -m 750 /srv/trophy/data /srv/trophy/data/ttClips/rerecord /srv/trophy/data/clips
install -d -m 755 /srv/trophy/weights
[ -f /etc/trophy/trophy.env ] || install -m 600 /dev/null /etc/trophy/trophy.env
[ -f /etc/trophy/caddy.env ] || install -m 600 /dev/null /etc/trophy/caddy.env
echo "done. Next: copy the env files and weights in (infra/vultr/README.md), then docker compose up."

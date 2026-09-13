#!/bin/bash
# Deploy Pgmnt to Raspberry Pi
# Usage: ./deploy-to-pi.sh [pi@duobrain.local]

set -e

PI_HOST="${1:-pi@duobrain.local}"
APP_SRC="/home/phil/Dev/Claude/Pgmnt"
APP_DEST="/opt/pgmnt/app"

echo "=== Deploying Pgmnt to $PI_HOST ==="

echo "Creating remote directories..."
ssh "$PI_HOST" "if [ ! -d /opt/pgmnt ]; then sudo mkdir -p /opt/pgmnt && sudo chown pi:pi /opt/pgmnt; fi && mkdir -p /opt/pgmnt/app /opt/pgmnt/logs"

echo "Syncing application files..."
rsync -avz --progress \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'data/' \
  --exclude '.env' \
  "$APP_SRC/" \
  "$PI_HOST:$APP_DEST/"

echo "Syncing gunicorn config..."
rsync -avz "$APP_SRC/deploy/gunicorn.conf.py" "$PI_HOST:/opt/pgmnt/"

if ssh "$PI_HOST" "test -f /opt/pgmnt/venv/bin/pip"; then
    echo "Installing dependencies..."
    ssh "$PI_HOST" "/opt/pgmnt/venv/bin/pip install -q -r $APP_DEST/requirements.txt"
    echo "Restarting service..."
    ssh "$PI_HOST" "sudo systemctl restart pgmnt"
    echo ""
    ssh "$PI_HOST" "sudo systemctl status pgmnt --no-pager | head -20"
else
    echo ""
    echo "Venv not set up yet. SSH in and run:"
    echo "  bash /opt/pgmnt/app/deploy/pi-setup.sh"
fi

echo ""
echo "=== Done ==="
ssh "$PI_HOST" "sudo systemctl status pgmnt --no-pager | head -20"

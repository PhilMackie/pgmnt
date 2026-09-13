#!/bin/bash
# Deploy Pgmnt to Raspberry Pi
# Usage: ./deploy-to-pi.sh [pi@duobrain.local]

set -e

PI_HOST="${1:-pi@duobrain.local}"
APP_SRC="/home/phil/Dev/Claude/Pgmnt"
APP_DEST="/opt/pgmnt/app"

echo "=== Deploying Pgmnt to $PI_HOST ==="

# Restarting the systemd service needs sudo, and the Pi has no passwordless
# sudo rule for it - that always requires a human typing a password at an
# actual terminal, so this script (run non-interactively) can't do it.
# It syncs code + deps only; restarting is a manual step printed at the end.
# (Matches Quanta's deploy-to-pi.sh convention.)

if ! ssh "$PI_HOST" "test -d /opt/pgmnt"; then
    echo "/opt/pgmnt doesn't exist yet on $PI_HOST."
    echo "SSH in and run the one-time setup first:"
    echo "  bash /opt/pgmnt/app/deploy/pi-setup.sh"
    exit 1
fi

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
else
    echo ""
    echo "Venv not set up yet. SSH in and run:"
    echo "  bash /opt/pgmnt/app/deploy/pi-setup.sh"
    exit 1
fi

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Next steps on the Pi:"
echo "  ssh $PI_HOST"
echo "  sudo systemctl restart pgmnt"
echo "  sudo systemctl status pgmnt"

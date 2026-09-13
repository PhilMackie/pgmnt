#!/bin/bash
# One-time Pgmnt setup on the Pi.
# Run ON THE PI: bash /opt/pgmnt/app/deploy/pi-setup.sh
# (Pi already has Python, venv support, UFW from duo-brain setup.)

set -e

echo "=== Pgmnt Pi Setup ==="

# Directories
sudo mkdir -p /opt/pgmnt
sudo chown pi:pi /opt/pgmnt
mkdir -p /opt/pgmnt/app /opt/pgmnt/logs

# Virtual environment
echo "Creating venv..."
python3 -m venv /opt/pgmnt/venv
/opt/pgmnt/venv/bin/pip install --upgrade pip -q

# .env
if [ ! -f /opt/pgmnt/app/.env ]; then
    echo ""
    echo "No .env found — creating one."
    echo "Enter PIN for Pgmnt (same as Quanta/Athena is fine):"
    read -s PIN
    PIN_HASH=$(python3 -c "import hashlib; print(hashlib.sha256('$PIN'.encode()).hexdigest())")
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    cat > /opt/pgmnt/app/.env << EOF
SECRET_KEY=$SECRET_KEY
AUTH_ENABLED=true
PIN_HASH=$PIN_HASH
PORT=5004
EOF
    chmod 600 /opt/pgmnt/app/.env
    echo ".env created."
fi

# Open firewall port
echo "Opening port 5004..."
sudo ufw allow 5004/tcp

# Systemd service
echo "Installing systemd service..."
sudo cp /opt/pgmnt/app/deploy/pgmnt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pgmnt
sudo systemctl start pgmnt

echo ""
sleep 2
sudo systemctl status pgmnt --no-pager
echo ""
echo "=== Pgmnt is running on port 5004 ==="
echo "Test: curl -I http://localhost:5004/login"

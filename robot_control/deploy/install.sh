#!/bin/bash
set -e

INSTALL_DIR="/opt/furance_robot"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

echo "=== Installing Robot Control System ==="

# 1. Create directories
echo "[1/5] Creating directories..."
mkdir -p "$INSTALL_DIR"/{bin,static,config,data/teach,logs,service}

# 2. Copy files
echo "[2/5] Copying files..."
if [ -d "$SCRIPT_DIR/dist/robot_control" ]; then
    cp -r "$SCRIPT_DIR/dist/robot_control/"* "$INSTALL_DIR/bin/"
else
    echo "Error: dist/robot_control/ not found. Run build.sh first."
    exit 1
fi

if [ -d "$SCRIPT_DIR/../../robot_control/frontend/dist" ]; then
    cp -r "$SCRIPT_DIR/../../robot_control/frontend/dist/"* "$INSTALL_DIR/static/"
fi

cp "$SCRIPT_DIR/config.yaml" "$INSTALL_DIR/config/"
cp "$SCRIPT_DIR/robot_control.service" "$INSTALL_DIR/service/"

# 3. Set permissions
echo "[3/5] Setting permissions..."
chmod +x "$INSTALL_DIR/bin/robot_control_server"
chown -R root:root "$INSTALL_DIR"

# 4. Install systemd service
echo "[4/5] Installing systemd service..."
cp "$INSTALL_DIR/service/robot_control.service" /etc/systemd/system/
systemctl daemon-reload

# 5. Enable and start
echo "[5/5] Enabling and starting service..."
systemctl enable robot_control
systemctl start robot_control

echo "=== Installation complete ==="
echo "Service status: systemctl status robot_control"
echo "Logs: journalctl -u robot_control -f"

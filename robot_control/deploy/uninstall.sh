#!/bin/bash
set -e

INSTALL_DIR="/opt/furance_robot"

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

echo "=== Uninstalling Robot Control System ==="

# 1. Stop and disable service
echo "[1/3] Stopping service..."
systemctl stop robot_control 2>/dev/null || true
systemctl disable robot_control 2>/dev/null || true
rm -f /etc/systemd/system/robot_control.service
systemctl daemon-reload

# 2. Remove files
echo "[2/3] Removing files..."
rm -rf "$INSTALL_DIR"

# 3. Confirm
echo "[3/3] Uninstallation complete"

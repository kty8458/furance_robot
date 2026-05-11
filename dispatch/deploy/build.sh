#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Building Dispatch System ==="

# 1. Install shared package
echo "[1/4] Installing shared package..."
cd "$PROJECT_ROOT/shared"
pip install -e .

# 2. Install backend dependencies
echo "[2/4] Installing backend dependencies..."
cd "$PROJECT_ROOT/dispatch/backend"
pip install -e .
pip install pyinstaller pyyaml

# 3. Build frontend
echo "[3/4] Building frontend..."
cd "$PROJECT_ROOT/dispatch/frontend"
npm install
npm run build

# 4. PyInstaller build
echo "[4/4] Running PyInstaller..."
cd "$SCRIPT_DIR"
pyinstaller dispatch.spec --noconfirm --clean

echo "=== Build complete: $SCRIPT_DIR/dist/dispatch/ ==="

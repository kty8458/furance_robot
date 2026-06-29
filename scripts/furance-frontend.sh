#!/bin/bash
# Wrapper for furance frontend (vite preview, served from dist/)
# 需要先 npm run build 生成 dist/
# 路径会在 install_autostart.sh 安装时替换

set -e

export HOME="__USER_HOME__"
PROJECT_ROOT="__PROJECT_ROOT__"
cd "$PROJECT_ROOT/robot_control/frontend"

# 加载 NVM 或系统 node
if [ -d "$HOME/.nvm" ]; then
    export NVM_DIR="$HOME/.nvm"
    set +u
    [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
    set -u
fi

# 如果还没有 node_modules 或 dist，自动初始化
if [ ! -d "node_modules" ]; then
    echo "node_modules 不存在，执行 npm install..."
    npm install
fi

if [ ! -d "dist" ]; then
    echo "dist 不存在，执行 npm run build..."
    npm run build
fi

exec npm run server

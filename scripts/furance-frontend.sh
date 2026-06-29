#!/bin/bash
# Wrapper for furance frontend (vite preview, served from dist/)
# 需要先 npm run build 生成 dist/
# 路径会在 install_autostart.sh 安装时替换

set -e

export HOME="__USER_HOME__"
PROJECT_ROOT="__PROJECT_ROOT__"
cd "$PROJECT_ROOT/robot_control/frontend"

# 加载 nvm (常见路径) 或系统 node
if [ -d "$HOME/.nvm" ]; then
    export NVM_DIR="$HOME/.nvm"
    set +u
    [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
    set -u
    # 显式加载默认/当前 node 版本到 PATH
    if [ -d "$NVM_DIR/versions/node" ]; then
        # 取最新版本目录
        NODE_BIN_DIR="$(ls -d $NVM_DIR/versions/node/v*/bin 2>/dev/null | sort -V | tail -1)"
        if [ -n "$NODE_BIN_DIR" ]; then
            export PATH="$NODE_BIN_DIR:$PATH"
        fi
    fi
fi

# 备选: 系统全局安装的 node
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# Source bashrc 兜底 (一些环境通过 bashrc 设置 PATH)
if [ -f "$HOME/.bashrc" ]; then
    set +u
    source "$HOME/.bashrc" 2>/dev/null || true
    set -u
fi

# 验证 npm 可用
if ! command -v npm >/dev/null 2>&1; then
    echo "ERROR: npm not found in PATH=$PATH" >&2
    exit 127
fi

echo "Using node: $(which node) ($(node --version 2>/dev/null))"
echo "Using npm:  $(which npm) ($(npm --version 2>/dev/null))"

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

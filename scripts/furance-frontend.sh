#!/bin/bash
# Wrapper for furance frontend (vite preview, served from dist/)
# 需要先 npm run build 生成 dist/
# 路径会在 install_autostart.sh 安装时替换

set -e

export HOME="__USER_HOME__"
PROJECT_ROOT="__PROJECT_ROOT__"
cd "$PROJECT_ROOT/robot_control/frontend"

# 1. 用 login shell 加载用户完整环境 (包括 .bashrc / .profile 中的 PATH)
# bash -lc 会触发 login shell init, 拿到用户 PATH
USER_PATH="$(bash -lc 'echo $PATH' 2>/dev/null || true)"
if [ -n "$USER_PATH" ]; then
    export PATH="$USER_PATH:$PATH"
fi

# 2. NVM 兜底
if [ -d "$HOME/.nvm" ]; then
    export NVM_DIR="$HOME/.nvm"
    set +u
    [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
    set -u
    NODE_BIN_DIR="$(ls -d $NVM_DIR/versions/node/v*/bin 2>/dev/null | sort -V | tail -1)"
    if [ -n "$NODE_BIN_DIR" ]; then
        export PATH="$NODE_BIN_DIR:$PATH"
    fi
fi

# 3. 手动解压的 node 兜底 (常见模式: $HOME/node-v*/bin)
for nbin in $HOME/node-v*/bin $HOME/.local/share/node*/bin; do
    if [ -d "$nbin" ]; then
        export PATH="$nbin:$PATH"
    fi
done

# 4. 验证
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

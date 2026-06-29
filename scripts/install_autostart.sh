#!/bin/bash
# 一次性安装 furance 控制系统的 systemd 自启动
# 功能:
#   1. 编译前端 (npm install + npm run build)
#   2. 替换 wrapper/service 中的路径占位符并复制到目标位置
#   3. 复制 systemd unit 到 /etc/systemd/system/
#   4. enable + start 三个服务
# 用法: ./install_autostart.sh

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
FRONTEND_DIR="$PROJECT_ROOT/robot_control/frontend"
SERVICES=(furance-node-manager furance-backend furance-frontend)

# 当前用户和家目录 (跨机部署时自动适配)
CURRENT_USER="$(id -un)"
USER_HOME="$HOME"

# ---- 颜色 ----
G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; N='\033[0m'
info()  { echo -e "${G}[INFO]${N} $*"; }
warn()  { echo -e "${Y}[WARN]${N} $*"; }
error() { echo -e "${R}[ERROR]${N} $*" >&2; }

# ---- 检查权限 ----
if [ "$EUID" -eq 0 ]; then
    error "请不要用 root 直接运行，脚本会在需要时调用 sudo"
    exit 1
fi

info "项目根目录: $PROJECT_ROOT"
info "前端目录: $FRONTEND_DIR"
info "当前用户: $CURRENT_USER (HOME=$USER_HOME)"

# ---- 占位符替换函数 ----
# 用法: render_template <src> <dst>
render_template() {
    local src="$1"
    local dst="$2"
    sed -e "s|__USER__|$CURRENT_USER|g" \
        -e "s|__USER_HOME__|$USER_HOME|g" \
        -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
        "$src" | sudo tee "$dst" > /dev/null
}

# ---- 1. 编译前端 ----
info "==========================="
info "步骤 1/4: 编译前端"
info "==========================="

cd "$FRONTEND_DIR"

# 加载 nvm (如果存在)
if [ -d "$HOME/.nvm" ]; then
    export NVM_DIR="$HOME/.nvm"
    [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
fi

if ! command -v npm &> /dev/null; then
    error "未找到 npm，请先安装 Node.js"
    exit 1
fi

if [ ! -d "node_modules" ]; then
    info "执行 npm install..."
    npm install
else
    info "node_modules 已存在，跳过 install"
fi

info "执行 npm run build..."
npm run build

if [ ! -d "dist" ]; then
    error "前端编译失败，未生成 dist 目录"
    exit 1
fi
info "前端编译完成: $FRONTEND_DIR/dist"

# ---- 2. 渲染并安装 wrapper 脚本 ----
info "==========================="
info "步骤 2/4: 安装 wrapper 脚本到 /usr/local/bin/ (替换路径占位符)"
info "==========================="

for svc in "${SERVICES[@]}"; do
    src="$SCRIPT_DIR/$svc.sh"
    dst="/usr/local/bin/$svc.sh"
    if [ ! -f "$src" ]; then
        error "$src 不存在"
        exit 1
    fi
    render_template "$src" "$dst"
    sudo chmod +x "$dst"
    info "  $svc.sh → $dst"
done

# ---- 3. 渲染并安装 systemd unit ----
info "==========================="
info "步骤 3/4: 安装 systemd unit 到 /etc/systemd/system/ (替换路径占位符)"
info "==========================="

for svc in "${SERVICES[@]}"; do
    src="$SCRIPT_DIR/$svc.service"
    dst="/etc/systemd/system/$svc.service"
    if [ ! -f "$src" ]; then
        error "$src 不存在"
        exit 1
    fi
    render_template "$src" "$dst"
    sudo chmod 644 "$dst"
    info "  $svc.service → $dst"
done

# ---- 4. 启动服务 ----
info "==========================="
info "步骤 4/4: 启动并启用服务"
info "==========================="

sudo systemctl daemon-reload

for svc in "${SERVICES[@]}"; do
    info "启用 $svc.service..."
    sudo systemctl enable "$svc.service"
    info "启动 $svc.service..."
    sudo systemctl restart "$svc.service"
done

sleep 2

# ---- 状态检查 ----
info "==========================="
info "服务状态:"
info "==========================="
for svc in "${SERVICES[@]}"; do
    if sudo systemctl is-active --quiet "$svc.service"; then
        info "  $svc: $(sudo systemctl is-active $svc.service)"
    else
        warn "  $svc: $(sudo systemctl is-active $svc.service) — 查看 journalctl -u $svc -n 50"
    fi
done

info "==========================="
info "安装完成! 访问:"
info "  前端: http://localhost:5173"
info "  后端: http://localhost:8000"
info ""
info "管理命令:"
info "  systemctl status furance-node-manager"
info "  systemctl status furance-backend"
info "  systemctl status furance-frontend"
info "  journalctl -u furance-backend -f"
info "==========================="

#!/bin/bash
# 一键启动全部开发服务
# 用法: ./scripts/dev.sh          (启动全部)
#       ./scripts/dev.sh stop     (停止全部)
#       ./scripts/dev.sh restart  (重启)
#       ./scripts/dev.sh status   (查看状态)

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$ROOT/.dev_pids"
LOG_DIR="$ROOT/.dev_logs"

# 端口配置
RC_BACKEND_PORT=8000
DP_BACKEND_PORT=8001
RC_FRONTEND_PORT=3000
DP_FRONTEND_PORT=3001

ALL_PORTS=($RC_BACKEND_PORT $DP_BACKEND_PORT $RC_FRONTEND_PORT $DP_FRONTEND_PORT)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

port_in_use() {
    fuser $1/tcp >/dev/null 2>&1
}

kill_port() {
    fuser -k $1/tcp >/dev/null 2>&1
}

# 轮询等待端口释放，最多等 timeout 秒
wait_port_free() {
    local port=$1 timeout=${2:-5}
    local i=0
    while port_in_use $port && [ $i -lt $timeout ]; do
        sleep 1
        i=$((i + 1))
    done
    ! port_in_use $port
}

# 轮询等待端口被监听，最多等 timeout 秒
wait_port_up() {
    local port=$1 timeout=${2:-8}
    local i=0
    while ! port_in_use $port && [ $i -lt $timeout ]; do
        sleep 1
        i=$((i + 1))
    done
    port_in_use $port
}

kill_all() {
    # 先按 PID 杀
    if [ -d "$PID_DIR" ]; then
        for pidfile in "$PID_DIR"/*.pid; do
            [ -f "$pidfile" ] || continue
            pid=$(cat "$pidfile")
            name=$(basename "$pidfile" .pid)
            kill $pid 2>/dev/null || true
            log_info "已停止: $name (PID $pid)"
        done
        rm -rf "$PID_DIR"
    fi

    # 用 fuser -k 强杀端口上的所有进程 (包括 uvicorn reload 子进程)
    for port in "${ALL_PORTS[@]}"; do
        if port_in_use $port; then
            kill_port $port
            log_info "清理端口 $port"
        fi
    done

    # 等待端口全部释放
    for port in "${ALL_PORTS[@]}"; do
        if ! wait_port_free $port 5; then
            log_warn "端口 $port 未能在 5s 内释放"
        fi
    done
}

start() {
    if [ -d "$PID_DIR" ]; then
        log_warn "服务已在运行，先运行 ./scripts/dev.sh stop"
        exit 1
    fi

    # 清理残留端口
    for port in "${ALL_PORTS[@]}"; do
        if port_in_use $port; then
            log_warn "端口 $port 有残留进程，清理中..."
            kill_port $port
            if ! wait_port_free $port 5; then
                log_error "端口 $port 无法释放，请手动处理: fuser -k $port/tcp"
                exit 1
            fi
        fi
    done

    mkdir -p "$PID_DIR" "$LOG_DIR"

    # 启动控制系统后端
    log_info "启动控制系统后端 (port $RC_BACKEND_PORT)..."
    cd "$ROOT/robot_control/backend"
    pip install -e . -q 2>>"$LOG_DIR/install.log" || true
    uvicorn app.main:app --host 0.0.0.0 --port $RC_BACKEND_PORT --reload \
        > "$LOG_DIR/rc_backend.log" 2>&1 &
    echo $! > "$PID_DIR/rc_backend.pid"

    # 启动调度系统后端
    log_info "启动调度系统后端 (port $DP_BACKEND_PORT)..."
    cd "$ROOT/dispatch/backend"
    pip install -e . -q 2>>"$LOG_DIR/install.log" || true
    mkdir -p data
    uvicorn app.main:app --host 0.0.0.0 --port $DP_BACKEND_PORT --reload \
        > "$LOG_DIR/dp_backend.log" 2>&1 &
    echo $! > "$PID_DIR/dp_backend.pid"

    # 启动控制系统前端
    log_info "启动控制系统前端 (port $RC_FRONTEND_PORT)..."
    cd "$ROOT/robot_control/frontend"
    [ -d node_modules ] || npm install --silent 2>>"$LOG_DIR/install.log"
    npx vite --port $RC_FRONTEND_PORT \
        > "$LOG_DIR/rc_frontend.log" 2>&1 &
    echo $! > "$PID_DIR/rc_frontend.pid"

    # 启动调度系统前端
    log_info "启动调度系统前端 (port $DP_FRONTEND_PORT)..."
    cd "$ROOT/dispatch/frontend"
    [ -d node_modules ] || npm install --silent 2>>"$LOG_DIR/install.log"
    npx vite --port $DP_FRONTEND_PORT \
        > "$LOG_DIR/dp_frontend.log" 2>&1 &
    echo $! > "$PID_DIR/dp_frontend.pid"

    # 等待端口就绪
    log_info "等待服务启动..."
    local failed=0
    for pair in "控制系统后端:$RC_BACKEND_PORT" "调度系统后端:$DP_BACKEND_PORT" "控制系统前端:$RC_FRONTEND_PORT" "调度系统前端:$DP_FRONTEND_PORT"; do
        name="${pair%%:*}"
        port="${pair##*:}"
        if wait_port_up $port; then
            log_info "$name 就绪 (port $port)"
        else
            log_error "$name 启动失败 (port $port)"
            log_file="${LOG_DIR}/${name%.*}.log"
            [ -f "$log_file" ] && tail -3 "$log_file"
            failed=1
        fi
    done

    if [ $failed -eq 1 ]; then
        log_error "部分服务启动失败，运行 ./scripts/dev.sh stop 清理"
        exit 1
    fi

    echo ""
    echo "========================================="
    log_info "全部服务已启动"
    echo "========================================="
    echo ""
    echo "  控制系统前端:  http://localhost:$RC_FRONTEND_PORT"
    echo "  控制系统后端:  http://localhost:$RC_BACKEND_PORT"
    echo "  控制系统API:   http://localhost:$RC_BACKEND_PORT/docs"
    echo ""
    echo "  调度系统前端:  http://localhost:$DP_FRONTEND_PORT"
    echo "  调度系统后端:  http://localhost:$DP_BACKEND_PORT"
    echo "  调度系统API:   http://localhost:$DP_BACKEND_PORT/docs"
    echo ""
    echo "  日志目录:  $LOG_DIR/"
    echo "  停止服务:  ./scripts/dev.sh stop"
    echo "========================================="

    # 持续显示后端日志 (Ctrl+C 退出, 服务继续运行)
    echo ""
    echo "--- 后端日志 (Ctrl+C 退出跟踪, 服务继续运行) ---"
    tail -f "$LOG_DIR/rc_backend.log" "$LOG_DIR/dp_backend.log" 2>/dev/null || true
}

stop() {
    log_info "停止全部服务..."
    kill_all
    log_info "全部服务已停止"
}

status() {
    echo "=== 服务状态 ==="
    for pair in "控制系统后端:$RC_BACKEND_PORT" "调度系统后端:$DP_BACKEND_PORT" "控制系统前端:$RC_FRONTEND_PORT" "调度系统前端:$DP_FRONTEND_PORT"; do
        name="${pair%%:*}"
        port="${pair##*:}"
        if port_in_use $port; then
            log_info "$name (port $port): 运行中"
        else
            log_warn "$name (port $port): 未运行"
        fi
    done
}

case "${1:-}" in
    stop)    stop ;;
    status)  status ;;
    restart) stop; start ;;
    *)       start ;;
esac

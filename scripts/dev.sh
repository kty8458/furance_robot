#!/bin/bash
# 一键启动全部开发服务
# 用法: ./scripts/dev.sh          (启动全部)
#       ./scripts/dev.sh stop     (停止全部)

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_DIR="$ROOT/.dev_pids"
LOG_DIR="$ROOT/.dev_logs"

# 端口配置
RC_BACKEND_PORT=8000
DP_BACKEND_PORT=8001
RC_FRONTEND_PORT=3000
DP_FRONTEND_PORT=3001

start() {
    if [ -d "$PID_DIR" ]; then
        echo "服务已在运行，先运行 ./scripts/dev.sh stop"
        exit 1
    fi

    mkdir -p "$PID_DIR" "$LOG_DIR"

    echo "=== 安装共享包 ==="
    cd "$ROOT/shared"
    pip install -e . -q 2>/dev/null

    echo "=== 启动控制系统后端 (port $RC_BACKEND_PORT) ==="
    cd "$ROOT/robot_control/backend"
    pip install -e . -q 2>/dev/null
    uvicorn app.main:app --host 0.0.0.0 --port $RC_BACKEND_PORT --reload \
        > "$LOG_DIR/rc_backend.log" 2>&1 &
    echo $! > "$PID_DIR/rc_backend.pid"

    echo "=== 启动调度系统后端 (port $DP_BACKEND_PORT) ==="
    cd "$ROOT/dispatch/backend"
    pip install -e . -q 2>/dev/null
    uvicorn app.main:app --host 0.0.0.0 --port $DP_BACKEND_PORT --reload \
        > "$LOG_DIR/dp_backend.log" 2>&1 &
    echo $! > "$PID_DIR/dp_backend.pid"

    echo "=== 启动控制系统前端 (port $RC_FRONTEND_PORT) ==="
    cd "$ROOT/robot_control/frontend"
    [ -d node_modules ] || npm install --silent
    npx vite --port $RC_FRONTEND_PORT \
        > "$LOG_DIR/rc_frontend.log" 2>&1 &
    echo $! > "$PID_DIR/rc_frontend.pid"

    echo "=== 启动调度系统前端 (port $DP_FRONTEND_PORT) ==="
    cd "$ROOT/dispatch/frontend"
    [ -d node_modules ] || npm install --silent
    npx vite --port $DP_FRONTEND_PORT \
        > "$LOG_DIR/dp_frontend.log" 2>&1 &
    echo $! > "$PID_DIR/dp_frontend.pid"

    # 等待服务就绪
    echo ""
    echo "等待服务启动..."
    sleep 3

    echo ""
    echo "========================================="
    echo "  全部服务已启动"
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

    # 持续显示后端日志 (Ctrl+C 退出)
    echo ""
    echo "--- 控制系统后端日志 (Ctrl+C 退出, 服务继续运行) ---"
    tail -f "$LOG_DIR/rc_backend.log" "$LOG_DIR/dp_backend.log" 2>/dev/null || true
}

stop() {
    if [ ! -d "$PID_DIR" ]; then
        echo "没有运行中的服务"
        exit 0
    fi

    echo "=== 停止全部服务 ==="
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        pid=$(cat "$pidfile")
        name=$(basename "$pidfile" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null && echo "  已停止: $name (PID $pid)"
        else
            echo "  已退出: $name (PID $pid)"
        fi
    done

    # 兜底: 杀死占用端口的进程
    for port in $RC_BACKEND_PORT $DP_BACKEND_PORT $RC_FRONTEND_PORT $DP_FRONTEND_PORT; do
        pid=$(lsof -ti:$port 2>/dev/null || true)
        [ -n "$pid" ] && kill $pid 2>/dev/null && echo "  清理端口 $port (PID $pid)"
    done

    rm -rf "$PID_DIR"
    echo "=== 全部服务已停止 ==="
}

status() {
    if [ ! -d "$PID_DIR" ]; then
        echo "没有运行中的服务"
        exit 0
    fi

    echo "=== 服务状态 ==="
    for pidfile in "$PID_DIR"/*.pid; do
        [ -f "$pidfile" ] || continue
        pid=$(cat "$pidfile")
        name=$(basename "$pidfile" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            echo "  运行中: $name (PID $pid)"
        else
            echo "  已停止: $name (PID $pid)"
        fi
    done
}

case "${1:-}" in
    stop)   stop ;;
    status) status ;;
    restart) stop; sleep 1; start ;;
    *)      start ;;
esac

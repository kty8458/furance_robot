#!/bin/bash
# Orin 部署机环境一键安装 (docs/orin_deploy.md 的脚本化版本)
#
# 用法:
#   ./scripts/install_orin_env.sh                 # 全部阶段
#   ./scripts/install_orin_env.sh --ros --dds     # 只跑指定阶段
#   ./scripts/install_orin_env.sh --list          # 查看阶段列表
#
# 阶段 (顺序与 docs/orin_deploy.md 章节对应):
#   ros       apt 安装 ROS2 Humble + MoveIt + CycloneDDS     (需 sudo)
#   dds       写 cyclonedds_profile.xml + ~/.bashrc 环境变量
#   vision    pip 安装视觉栈依赖 + Orbbec udev 规则          (udev 需 sudo)
#   soem      编译 SOEM (EtherCAT 夹爪前置)
#   build     colcon build 全量工作空间
#   backend   pip 安装控制系统后端 (shared + robot_control)
#   node      Node.js 22 安装 (apt 方式)                     (需 sudo)
#   frontend  npm install 前端依赖
#
# 前提: 系统已刷 JetPack (Ubuntu 22.04), 项目代码已 clone 到本目录, 网络可达。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ROS_WS="$PROJECT_ROOT/ros2_ws"
VISION_DIR="$ROS_WS/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

ALL_STAGES=(ros dds vision soem build backend node frontend)

stage_ros() {
    log_info "[ros] apt 安装 ROS2 Humble + MoveIt (需要 sudo)"
    sudo apt update
    sudo apt install -y \
        ros-humble-desktop \
        ros-humble-moveit \
        ros-humble-rmw-cyclonedds-cpp \
        ros-humble-controller-manager \
        ros-humble-joint-state-publisher \
        ros-humble-joint-state-publisher-gui \
        ros-humble-ros2launch \
        ros-humble-rosidl-generator-dds-idl \
        python3-colcon-common-extensions \
        python3-pip \
        build-essential cmake

    local ok=0
    # 注意: 必须临时关 -e -u 再 source ROS setup 脚本 (set -u 下其引用的
    # AMENT_TRACE_SETUP_FILES 等未定义变量会静默终止整个安装脚本, Orin 实测踩坑)
    set +eu
    # shellcheck disable=SC1091
    source /opt/ros/humble/setup.bash 2>/dev/null
    set -eu
    for pkg in moveit_kinematics moveit_ros_move_group rmw_cyclonedds_cpp; do
        ros2 pkg list 2>/dev/null | grep -q "^${pkg}$" || { log_error "缺少 $pkg"; ok=1; }
    done
    # 接口包编译必需, 不在任何元包依赖树里 (见 docs/orin_deploy.md 1.1)
    dpkg -s ros-humble-rosidl-generator-dds-idl >/dev/null 2>&1 \
        || { log_error "缺少 ros-humble-rosidl-generator-dds-idl (接口包编译会失败)"; ok=1; }
    [ $ok -eq 0 ] && log_info "[ros] 验证通过" || log_warn "[ros] 验证有缺项, 检查上方输出"
}

stage_dds() {
    log_info "[dds] 写入 CycloneDDS 配置"
    mkdir -p "$HOME/.ros"
    local profile="$HOME/.ros/cyclonedds_profile.xml"
    if [ -f "$profile" ]; then
        log_warn "[dds] $profile 已存在, 跳过 (如需重置请手动删除后重跑)"
    else
        cat > "$profile" <<'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS xmlns="https://cdds.io/config">
    <Domain id="any">
        <General>
            <Interfaces>
                <NetworkInterface name="lo" />
            </Interfaces>
            <AllowMulticast>default</AllowMulticast>
        </General>
    </Domain>
</CycloneDDS>
EOF
        log_info "[dds] 已写入 $profile"
    fi

    log_info "[dds] 追加环境变量到 ~/.bashrc (幂等)"
    local brc="$HOME/.bashrc"
    add_env() {
        grep -qF "$1" "$brc" || echo "$1" >> "$brc"
    }
    add_env 'export ROS_DOMAIN_ID=45'
    add_env 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp'
    add_env 'export CYCLONEDDS_URI=file://$HOME/.ros/cyclonedds_profile.xml'
    grep -qF 'source /opt/ros/humble/setup.bash' "$brc" || \
        echo '[ -f /opt/ros/humble/setup.bash ] && source /opt/ros/humble/setup.bash' >> "$brc"
    log_info "[dds] 完成 (新终端生效)"
}

pip_install() {
    # Ubuntu 23.04+ 的 pip 拒绝装系统 python (PEP 668), 22.04 一般不需要
    pip3 install "$@" || pip3 install --break-system-packages "$@"
}

stage_vision() {
    log_info "[vision] pip 安装视觉栈依赖"
    [ -f "$VISION_DIR/requirements-orin.txt" ] || { log_error "找不到 $VISION_DIR/requirements-orin.txt"; exit 1; }
    pip_install -r "$VISION_DIR/requirements-orin.txt"

    log_info "[vision] 安装 Orbbec udev 规则 (需要 sudo, pip 不会自动装)"
    local sdk_dir
    sdk_dir="$(python3 -c "import pyorbbecsdk, os; print(os.path.dirname(pyorbbecsdk.__file__))")"
    sudo "$sdk_dir/shared/install_udev_rules.sh"
    [ -f /etc/udev/rules.d/99-obsensor-libusb.rules ] && log_info "[vision] udev 规则已就位" \
        || log_warn "[vision] udev 规则未找到, 手动检查 $sdk_dir/shared/"

    python3 -c "from pyorbbecsdk import Pipeline; print('[vision] pyorbbecsdk ok')" || true
    python3 -c "import onnxruntime, cv2.aruco, yaml, numpy; print('[vision] 依赖 ok')" || true
}

stage_soem() {
    local soem="$ROS_WS/src/SOEM"
    if [ -f "$soem/install/lib/libsoem.a" ]; then
        log_info "[soem] libsoem.a 已存在, 跳过"
        return
    fi
    log_info "[soem] 克隆并编译 SOEM v1.4.0"
    if [ ! -d "$soem" ]; then
        git clone https://github.com/OpenEtherCATsociety/SOEM.git "$soem"
    fi
    ( cd "$soem" && git checkout v1.4.0 && \
      mkdir -p build && cd build && \
      cmake -DCMAKE_INSTALL_PREFIX=../install .. && \
      make -j"$(nproc)" && make install )
    [ -f "$soem/install/lib/libsoem.a" ] && log_info "[soem] 编译成功" \
        || { log_error "[soem] libsoem.a 缺失"; exit 1; }
}

stage_build() {
    log_info "[build] colcon build 全量工作空间"
    [ -d "$ROS_WS/src" ] || { log_error "找不到 $ROS_WS/src"; exit 1; }
    # 同 stage_ros: 关 -e -u 再 source (set -u 下 setup.bash 的未定义变量会杀掉脚本)
    set +eu
    # shellcheck disable=SC1091
    source /opt/ros/humble/setup.bash
    set -eu
    ( cd "$ROS_WS" && colcon build --symlink-install )
    log_info "[build] 完成。source $ROS_WS/install/setup.bash 后可用"
}

stage_backend() {
    log_info "[backend] pip 安装控制系统后端"
    ( cd "$PROJECT_ROOT/shared" && pip_install -e . )
    ( cd "$PROJECT_ROOT/robot_control/backend" && pip_install -e ".[dev]" )
    python3 -c "import fastapi, uvicorn, pydantic; print('[backend] 依赖 ok')" || true
}

stage_node() {
    if command -v node >/dev/null 2>&1 && [ "$(node -v | cut -dv -f2 | cut -d. -f1)" -ge 18 ]; then
        log_info "[node] 已有 node $(node -v), 跳过"
        return
    fi
    log_info "[node] 安装 Node.js 22 (需要 sudo)"
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt install -y nodejs
    log_info "[node] node $(node -v) / npm $(npm -v)"
}

stage_frontend() {
    log_info "[frontend] npm install"
    command -v npm >/dev/null 2>&1 || { log_error "npm 不存在, 先跑 --node 阶段"; exit 1; }
    ( cd "$PROJECT_ROOT/robot_control/frontend" && npm install )
    log_info "[frontend] 完成 (生产构建由 install_autostart.sh 的 npm run build 完成)"
}

# ---------- 参数解析 ----------
if [ "${1:-}" = "--list" ]; then
    echo "可用阶段: ${ALL_STAGES[*]}"
    echo "用法: $0 [--ros --dds --vision ...]   (无参数 = 全部)"
    exit 0
fi

STAGES=()
if [ $# -eq 0 ]; then
    STAGES=("${ALL_STAGES[@]}")
else
    for s in "$@"; do
        s="${s#--}"
        if printf '%s\n' "${ALL_STAGES[@]}" | grep -qx "$s"; then
            STAGES+=("$s")
        else
            log_error "未知阶段: $s (用 --list 查看)"
            exit 1
        fi
    done
fi

log_info "将执行阶段: ${STAGES[*]}"
log_info "项目根目录: $PROJECT_ROOT"

for s in "${STAGES[@]}"; do
    "stage_$s"
done

echo
log_info "全部完成。后续步骤见 docs/orin_deploy.md 第 5 节 (数据恢复) 和第 6 节 (install_autostart.sh)"

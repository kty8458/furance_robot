#!/bin/bash
# Wrapper for furance backend (FastAPI + uvicorn)
# 后端也需要 ROS2 环境才能与 ROS2 节点通讯
# 路径会在 install_autostart.sh 安装时替换

set -e

# 用户环境 (安装时替换)
export HOME="__USER_HOME__"
PROJECT_ROOT="__PROJECT_ROOT__"
cd "$PROJECT_ROOT/robot_control/backend"

# Source 用户 bashrc
if [ -f "$HOME/.bashrc" ]; then
    set +u
    source "$HOME/.bashrc"
    set -u
fi

# 核心环境变量 (与 node_manager 一致)
export ROS_DOMAIN_ID=45
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI="file://$HOME/.ros/cyclonedds_profile.xml"

# Source ROS2 install
if [ -f "/opt/ros/humble/setup.bash" ]; then
    set +u
    source /opt/ros/humble/setup.bash
    set -u
fi

# Source workspace install
if [ -f "$PROJECT_ROOT/ros2_ws/install/setup.bash" ]; then
    set +u
    source "$PROJECT_ROOT/ros2_ws/install/setup.bash"
    set -u
fi

# 启动后端服务 (使用系统 python)
export ROS2_MODE=real
exec /usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

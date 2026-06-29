#!/bin/bash
# Wrapper for furance node_manager (ROS2)
# 加载完整 ROS2 环境后启动 node_manager
# 路径会在 install_autostart.sh 安装时替换

set -e

# 用户环境 (安装时替换)
export HOME="__USER_HOME__"
PROJECT_ROOT="__PROJECT_ROOT__"
cd "$PROJECT_ROOT"

# Source 用户 bashrc (加载 ROS2_DISTRO 等)
if [ -f "$HOME/.bashrc" ]; then
    set +u
    source "$HOME/.bashrc"
    set -u
fi

# 核心环境变量
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

# 启动 node_manager
exec ros2 run furance_sim node_manager

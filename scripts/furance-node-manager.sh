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

# 相机标定数据 (内参/手眼/场景) 与示教/工作流数据同路径存储
# camera_manager_node 与 camera_calibration.py 均读取此变量
export CAMERA_CONFIG_PATH="$PROJECT_ROOT/robot_control/backend/data/camera/robot_001/camera_config.yaml"

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

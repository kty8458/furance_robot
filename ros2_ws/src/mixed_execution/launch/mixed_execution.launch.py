"""混合执行服务启动文件。"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="mixed_execution",
            executable="mixed_executor_node",
            name="mixed_executor",
            output="screen",
        ),
    ])

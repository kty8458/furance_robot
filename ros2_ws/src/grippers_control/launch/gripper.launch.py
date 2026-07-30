from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    default_config = os.path.join(
        get_package_share_directory("grippers_control"),
        "config",
        "gripper.yaml",
    )

    config_arg = DeclareLaunchArgument(
        "config",
        default_value=default_config,
        description="Path to the gripper node parameter file.",
    )

    gripper_node = Node(
        package="grippers_control",
        executable="gripper_node",
        name="gripper_node",
        output="screen",
        parameters=[LaunchConfiguration("config")],
    )

    return LaunchDescription([config_arg, gripper_node])

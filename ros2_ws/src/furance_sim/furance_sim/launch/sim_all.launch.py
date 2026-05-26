import os

from launch import LaunchDescription
from launch.actions import SetEnvironmentVariable
from launch_ros.actions import Node


def generate_launch_description():
    furance_root = os.environ.get('FURANCE_ROBOT_ROOT', '')

    nodes = [
        Node(
            package='furance_sim',
            executable='gripper_node',
            name='gripper_node',
            output='screen',
        ),
        Node(
            package='furance_sim',
            executable='command_node',
            name='command_node',
            output='screen',
        ),
        Node(
            package='furance_sim',
            executable='node_manager',
            name='node_manager',
            output='screen',
        ),
    ]

    actions = []
    if furance_root:
        actions.append(SetEnvironmentVariable('FURANCE_ROBOT_ROOT', furance_root))
    actions.extend(nodes)

    return LaunchDescription(actions)

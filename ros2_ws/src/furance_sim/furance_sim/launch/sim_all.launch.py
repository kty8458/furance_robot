from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='furance_sim',
            executable='navigation_node',
            name='navigation_node',
            output='screen',
        ),
        Node(
            package='furance_sim',
            executable='arm_node',
            name='arm_node',
            output='screen',
        ),
        Node(
            package='furance_sim',
            executable='gripper_node',
            name='gripper_node',
            output='screen',
        ),
        Node(
            package='furance_sim',
            executable='status_node',
            name='status_node',
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
    ])

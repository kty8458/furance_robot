import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, GroupAction, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    enable_camera_1 = LaunchConfiguration("enable_camera_1")
    enable_camera_2 = LaunchConfiguration("enable_camera_2")
    enable_camera_3 = LaunchConfiguration("enable_camera_3")
    enable_rviz = LaunchConfiguration("enable_rviz")

    declare_enable_camera_1 = DeclareLaunchArgument(
        "enable_camera_1", default_value="true", description="Launch camera_1"
    )
    declare_enable_camera_2 = DeclareLaunchArgument(
        "enable_camera_2", default_value="false", description="Launch camera_2"
    )
    declare_enable_camera_3 = DeclareLaunchArgument(
        "enable_camera_3", default_value="false", description="Launch camera_3"
    )
    declare_enable_rviz = DeclareLaunchArgument(
        "enable_rviz", default_value="false", description="Launch RViz2 for camera visualization"
    )

    orbbec_launch_dir = os.path.join(
        get_package_share_directory("orbbec_camera"), "launch"
    )
    orbbec_launch_file = os.path.join(orbbec_launch_dir, "orbbec_camera.launch.py")

    # Camera 1 — head camera
    camera_1 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(orbbec_launch_file),
        launch_arguments={
            "camera_name": "camera_1",
            "usb_port": "2-1",
            "device_num": "3",
            "sync_mode": "standalone",
        }.items(),
    )

    # Camera 2 — left arm camera
    camera_2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(orbbec_launch_file),
        launch_arguments={
            "camera_name": "camera_2",
            "usb_port": "2-2",
            "device_num": "3",
            "sync_mode": "standalone",
        }.items(),
    )

    # Camera 3 — right arm camera
    camera_3 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(orbbec_launch_file),
        launch_arguments={
            "camera_name": "camera_3",
            "usb_port": "2-3",
            "device_num": "3",
            "sync_mode": "standalone",
        }.items(),
    )

    vision_detect_node = Node(
        package="python_pkgs",
        executable="vision_detect",
        name="vision_detect_node",
        output="screen",
    )

    pkg_share = get_package_share_directory("python_pkgs")
    rviz_config = os.path.join(pkg_share, "config", "three_cameras.rviz")

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=["-d", rviz_config],
        condition=None,  # always add, controlled by if-condition below
    )

    ld = LaunchDescription()
    ld.add_action(declare_enable_camera_1)
    ld.add_action(declare_enable_camera_2)
    ld.add_action(declare_enable_camera_3)
    ld.add_action(declare_enable_rviz)

    # Stagger camera launches to avoid USB contention and bandwidth spikes.
    ld.add_action(TimerAction(
        period=0.0,
        actions=[GroupAction([camera_1], condition=IfCondition(enable_camera_1))],
    ))
    ld.add_action(TimerAction(
        period=2.0,
        actions=[GroupAction([camera_2], condition=IfCondition(enable_camera_2))],
    ))
    ld.add_action(TimerAction(
        period=4.0,
        actions=[GroupAction([camera_3], condition=IfCondition(enable_camera_3))],
    ))
    ld.add_action(TimerAction(period=6.0, actions=[GroupAction([vision_detect_node])]))

    rviz_node.condition = IfCondition(enable_rviz)
    ld.add_action(TimerAction(period=8.0, actions=[GroupAction([rviz_node])]))

    return ld

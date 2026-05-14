import os
import math
import yaml
import re

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.parameter_descriptions import ParameterValue

from ament_index_python.packages import get_package_share_directory


def construct_angle_radians(loader, node):
    value = loader.construct_scalar(node)
    try:
        return float(value)
    except SyntaxError:
        raise Exception("invalid expression: %s" % value)


def construct_angle_degrees(loader, node):
    return math.radians(construct_angle_radians(loader, node))


def load_yaml(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)

    try:
        yaml.SafeLoader.add_constructor("!radians", construct_angle_radians)
        yaml.SafeLoader.add_constructor("!degrees", construct_angle_degrees)
    except Exception:
        raise Exception("yaml support not available; install python-yaml")

    try:
        with open(absolute_file_path) as file:
            return yaml.safe_load(file)
    except OSError:
        return None


def launch_setup(context, *args, **kwargs):
    description_package = LaunchConfiguration("description_package")
    description_file = LaunchConfiguration("description_file")
    moveit_config_package = LaunchConfiguration("moveit_config_package")
    moveit_joint_limits_file = LaunchConfiguration("moveit_joint_limits_file")
    moveit_config_file = LaunchConfiguration("moveit_config_file")
    use_sim_time = LaunchConfiguration("use_sim_time")
    use_sim = LaunchConfiguration("use_sim")

    robot_description_content = Command(
        [
            PathJoinSubstitution([FindExecutable(name="xacro")]),
            " ",
            PathJoinSubstitution([FindPackageShare(description_package), "config", description_file]),
        ]
    )
    robot_description = {"robot_description": robot_description_content}

    robot_description_semantic_content = Command(
        [
            PathJoinSubstitution([FindExecutable(name="xacro")]),
            " ",
            PathJoinSubstitution(
                [FindPackageShare(moveit_config_package), "config", moveit_config_file]
            ),
        ]
    )
    robot_description_semantic = {
        "robot_description_semantic": ParameterValue(robot_description_semantic_content, value_type=str)
    }

    robot_description_kinematics = PathJoinSubstitution(
        [FindPackageShare(moveit_config_package), "config", "kinematics.yaml"]
    )

    robot_description_planning = {
        "robot_description_planning": load_yaml(
            str(moveit_config_package.perform(context)),
            os.path.join("config", str(moveit_joint_limits_file.perform(context))),
        )
    }

    ompl_planning_pipeline_config = {
        "move_group": {
            "planning_plugin": "ompl_interface/OMPLPlanner",
            "request_adapters": """default_planner_request_adapters/AddTimeOptimalParameterization
                                default_planner_request_adapters/FixWorkspaceBounds
                                default_planner_request_adapters/FixStartStateBounds
                                default_planner_request_adapters/FixStartStateCollision
                                default_planner_request_adapters/FixStartStatePathConstraints""",
            "start_state_max_bounds_error": 0.1,
        }
    }
    ompl_planning_yaml = load_yaml("t1_moveit_config", "config/ompl_planning.yaml")
    ompl_planning_pipeline_config["move_group"].update(ompl_planning_yaml)

    controllers_yaml = load_yaml("t1_moveit_config", "config/moveit_controllers.yaml")

    moveit_controllers = {
        "moveit_simple_controller_manager": controllers_yaml,
        "moveit_controller_manager": "moveit_simple_controller_manager/MoveItSimpleControllerManager",
        "trajectory_execution": {
            "allowed_execution_duration_scaling": 2.0,
            "allowed_goal_duration_margin": 0.5,
            "allowed_start_tolerance": 0.01,
        }
    }

    trajectory_execution = {
        "moveit_manage_controllers": False,
        "trajectory_execution.allowed_execution_duration_scaling": 1.2,
        "trajectory_execution.allowed_goal_duration_margin": 0.5,
        "trajectory_execution.allowed_start_tolerance": 0.01,
    }

    planning_scene_monitor_parameters = {
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
        "publish_robot_description": True,
        "publish_robot_description_semantic": True,
    }

    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        respawn=True,
        parameters=[
            robot_description,
            robot_description_semantic,
            robot_description_kinematics,
            robot_description_planning,
            ompl_planning_yaml,
            ompl_planning_pipeline_config,
            trajectory_execution,
            moveit_controllers,
            planning_scene_monitor_parameters,
            {"use_sim_time": True if use_sim.perform(context) == "true" else use_sim_time},
        ],
    )

    node_robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[robot_description],
        output='screen'
    )

    pkg_path = get_package_share_directory('t1_description')
    urdf_file = os.path.join(pkg_path, 'urdf', 't1.urdf')
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()
        target_robot_desc = re.sub(
            r'rgba="([\d\.]+) ([\d\.]+) ([\d\.]+) ([\d\.]+)"',
            r'rgba="\1 \2 1.0 0.3"',
            robot_desc
        )
    target_model = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        namespace='target',
        name='robot_state_publisher_target',
        output='screen',
        parameters=[
            {'robot_description': target_robot_desc},
            {'frame_prefix': 'target/'}
        ],
    )

    target_base_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_base_to_target',
        arguments=['0', '0', '0', '0', '0', '0', 'base_link', 'target/base_link'],
        output='screen'
    )

    joint_states_bridge = Node(
        package='python_pkgs',
        executable='t1_joint_state_bridge',
        output='screen',
    )

    controller = Node(
        package='python_pkgs' if use_sim.perform(context) == "true" else 'arm_controller',
        executable='sim_arm_controller' if use_sim.perform(context) == "true" else 'moveit_arm_controller',
        output='screen',
    )

    move_service = Node(
        package='t1_moveit_config',
        executable='t1_moveit_server'
    )

    nodes_to_start = [
        joint_states_bridge,
        target_base_tf,
        target_model,
        controller,
        move_group_node,
        node_robot_state_publisher,
        move_service,
    ]

    return nodes_to_start


def generate_launch_description():
    declared_arguments = []
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_package",
            default_value="t1_moveit_config",
            description="Description package with robot URDF/XACRO files.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_file",
            default_value="t1.urdf.xacro",
            description="URDF/XACRO description file with the robot.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "moveit_config_package",
            default_value="t1_moveit_config",
            description="MoveIt config package with robot SRDF/XACRO files.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "moveit_config_file",
            default_value="t1.srdf",
            description="MoveIt SRDF/XACRO description file with the robot.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "moveit_joint_limits_file",
            default_value="joint_limits.yaml",
            description="MoveIt joint limits.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="false",
            description="Make MoveIt use simulation time.",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "use_sim",
            default_value="true",
            description="Use sim arm controller instead of real hardware.",
        )
    )

    return LaunchDescription(declared_arguments + [OpaqueFunction(function=launch_setup)])
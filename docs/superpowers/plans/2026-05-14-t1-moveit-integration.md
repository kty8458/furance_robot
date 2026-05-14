# T1 MoveIt Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate T1 robot's MoveIt configuration with the robot_control backend — fix deps, create headless launch, add RViz launch, connect status monitoring to /joint_states, implement MoveP/MoveL via direct ROS2 service calls.

**Architecture:** The backend (FastAPI) will add a `MoveItServiceClient` for typed MoveP/MoveL service calls and a `JointStateListener` for subscribing to /joint_states. A new headless `t1_moveit.launch.py` replaces the GUI-heavy original. The status pipeline merges arm data from /joint_states into the existing WebSocket status stream.

**Tech Stack:** ROS2 Humble, MoveIt2, FastAPI, Vue 3, Pydantic v2, sensor_msgs, control_interfaces

---

## File Structure

### New files
- `ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_moveit_headless.launch.py` — headless MoveIt launch
- `ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_rviz.launch.py` — standalone RViz launch for debugging
- `robot_control/backend/app/ros2/moveit_client.py` — MoveIt service client (MoveP/MoveL)
- `robot_control/backend/app/ros2/joint_state_listener.py` — /joint_states subscriber + TF lookup

### Modified files
- `ros2_ws/src/t1_robot/python_pkgs/package.xml` — add missing dependencies
- `ros2_ws/src/t1_robot/python_pkgs/setup.py` — add missing install_requires
- `robot_control/backend/app/ros2/factory.py` — create MoveItServiceClient + JointStateListener
- `robot_control/backend/app/ros2/runtime.py` — add subprocess launch management
- `robot_control/backend/app/services/arm_service.py` — use MoveItServiceClient for movep/moveL
- `robot_control/backend/app/services/ros2_manager.py` — add launch file start/stop
- `robot_control/backend/app/api/ros2_nodes.py` — add launch start/stop endpoints
- `robot_control/backend/app/main.py` — start/stop new components

---

## Task 1: Fix python_pkgs package.xml Dependencies

**Files:**
- Modify: `ros2_ws/src/t1_robot/python_pkgs/package.xml`

- [ ] **Step 1: Update package.xml with all missing exec_depend entries**

Replace the entire `<package>` content with:

```xml
<?xml version="1.0"?>
<?xml-model href="http://download.ros.org/schema/package_format3.xsd" schematypens="http://www.w3.org/2001/XMLSchema"?>
<package format="3">
  <name>python_pkgs</name>
  <version>0.0.0</version>
  <description>T1 robot auxiliary Python packages</description>
  <maintainer email="banwf@foxmail.com">baosight</maintainer>
  <license>Apache-2.0</license>

  <buildtool_depend>ament_cmake</buildtool_depend>
  <build_depend>ament_python</build_depend>
  <exec_depend>ament_python</exec_depend>

  <exec_depend>rclpy</exec_depend>
  <exec_depend>sensor_msgs</exec_depend>
  <exec_depend>trajectory_msgs</exec_depend>
  <exec_depend>control_msgs</exec_depend>
  <exec_depend>control_interfaces</exec_depend>
  <exec_depend>geometry_msgs</exec_depend>
  <exec_depend>std_msgs</exec_depend>
  <exec_depend>interface_pkg</exec_depend>
  <exec_depend>joint_state_publisher</exec_depend>
  <exec_depend>python_qt_binding</exec_depend>

  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
```

- [ ] **Step 2: Update setup.py install_requires**

In `ros2_ws/src/t1_robot/python_pkgs/setup.py`, change:

```python
    install_requires=['setuptools'],
```

to:

```python
    install_requires=['setuptools'],
    extras_require={
        'qt': ['PyQt5'],
    },
```

(Don't add ROS2 packages to install_requires — they come via rosdep/apt, not pip.)

- [ ] **Step 3: Commit**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/package.xml ros2_ws/src/t1_robot/python_pkgs/setup.py
git commit -m "fix: add missing dependencies to python_pkgs package.xml"
```

---

## Task 2: Create Headless MoveIt Launch File

**Files:**
- Create: `ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_moveit_headless.launch.py`

This is derived from the existing `t1_moveit.launch.py` with these changes:
1. Remove rviz_node entirely
2. Remove service_control_gui (t1_joint_state_publisher_gui — requires Qt display)
3. Fix arm_controller package reference: `package='arm_controller'` → `package='python_pkgs'`, executable stays `sim_arm_controller`
4. Add `use_sim` parameter (default "true") to control sim vs real arm controller
5. Default `launch_rviz` to "false"
6. Keep target_model + target_base_tf (they don't need display)

- [ ] **Step 1: Create t1_moveit_headless.launch.py**

Create `ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_moveit_headless.launch.py`:

```python
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

    # Target visualization (no display needed)
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

    # Arm controller: sim uses python_pkgs, real uses arm_controller package
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
```

- [ ] **Step 2: Commit**

```bash
git add ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_moveit_headless.launch.py
git commit -m "feat: add headless MoveIt launch file for t1"
```

---

## Task 3: Create Standalone RViz Launch File

**Files:**
- Create: `ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_rviz.launch.py`

This launch starts only RViz2 with the MoveIt configuration. It assumes the MoveIt launch is already running.

- [ ] **Step 1: Create t1_rviz.launch.py**

Create `ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_rviz.launch.py`:

```python
import os

from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.parameter_descriptions import ParameterValue

from ament_index_python.packages import get_package_share_directory
import yaml
import math


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
    moveit_config_file = LaunchConfiguration("moveit_config_file")

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

    ompl_planning_yaml = load_yaml("t1_moveit_config", "config/ompl_planning.yaml")
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
    ompl_planning_pipeline_config["move_group"].update(ompl_planning_yaml)

    robot_description_planning = load_yaml("t1_moveit_config", "config/joint_limits.yaml")

    rviz_config_file = PathJoinSubstitution(
        [FindPackageShare(moveit_config_package), "config", "moveit.rviz"]
    )

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2_moveit",
        output="log",
        arguments=["-d", rviz_config_file],
        parameters=[
            robot_description,
            robot_description_semantic,
            ompl_planning_pipeline_config,
            robot_description_kinematics,
            {"robot_description_planning": robot_description_planning},
        ],
    )

    return [rviz_node]


def generate_launch_description():
    declared_arguments = []
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_package",
            default_value="t1_moveit_config",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "description_file",
            default_value="t1.urdf.xacro",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "moveit_config_package",
            default_value="t1_moveit_config",
        )
    )
    declared_arguments.append(
        DeclareLaunchArgument(
            "moveit_config_file",
            default_value="t1.srdf",
        )
    )

    return LaunchDescription(declared_arguments + [OpaqueFunction(function=launch_setup)])
```

- [ ] **Step 2: Commit**

```bash
git add ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_rviz.launch.py
git commit -m "feat: add standalone RViz launch for t1 debugging"
```

---

## Task 4: Add JointStateListener to Backend

**Files:**
- Create: `robot_control/backend/app/ros2/joint_state_listener.py`
- Modify: `robot_control/backend/app/ros2/factory.py`
- Modify: `robot_control/backend/app/main.py`

This listener subscribes to `/joint_states` (sensor_msgs/JointState), extracts left/right arm joint angles, and pushes arm data to StatusService. It merges with existing `/robot_status` data rather than replacing it.

- [ ] **Step 1: Create joint_state_listener.py**

Create `robot_control/backend/app/ros2/joint_state_listener.py`:

```python
import asyncio
import logging
import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.status_service import StatusService

try:
    from sensor_msgs.msg import JointState

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False

LEFT_JOINT_NAMES = [f"ARM-L-J{i}_Joint" for i in range(1, 8)]
RIGHT_JOINT_NAMES = [f"ARM-R-J{i}_Joint" for i in range(1, 8)]


class JointStateListenerBase(ABC):
    @abstractmethod
    async def start(self, status_service: "StatusService"):
        ...

    @abstractmethod
    async def stop(self):
        ...


class MockJointStateListener(JointStateListenerBase):
    async def start(self, status_service: "StatusService"):
        pass

    async def stop(self):
        pass


class RealJointStateListener(JointStateListenerBase):
    """Subscribes to /joint_states and pushes arm data to StatusService.

    Extracts left/right arm joint angles from JointState messages and
    merges them into the existing status data.
    """

    JOINT_STATES_TOPIC = "/joint_states"

    def __init__(self, runtime):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed")
        self._runtime = runtime
        self._sub = None
        self._status_service: "StatusService | None" = None

    async def start(self, status_service: "StatusService"):
        self._status_service = status_service
        node = self._runtime.node
        self._sub = node.create_subscription(
            JointState,
            self.JOINT_STATES_TOPIC,
            self._on_joint_state,
            10,
        )
        logger.info("Subscribed to %s", self.JOINT_STATES_TOPIC)

    async def stop(self):
        if self._sub and self._runtime.is_running:
            self._runtime.node.destroy_subscription(self._sub)
            self._sub = None
            logger.info("Unsubscribed from %s", self.JOINT_STATES_TOPIC)

    def _on_joint_state(self, msg: JointState):
        if self._status_service is None:
            return

        left_angles = [0.0] * 7
        right_angles = [0.0] * 7

        name_to_index = {name: i for i, name in enumerate(msg.name)}

        for i, name in enumerate(LEFT_JOINT_NAMES):
            if name in name_to_index:
                idx = name_to_index[name]
                left_angles[i] = math.degrees(msg.position[idx])

        for i, name in enumerate(RIGHT_JOINT_NAMES):
            if name in name_to_index:
                idx = name_to_index[name]
                right_angles[i] = math.degrees(msg.position[idx])

        arm_data = {
            "arm": {
                "left": {
                    "joint_angles": left_angles,
                    "end_effector": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    "coordinate_frame": "base_link",
                    "status": "idle",
                },
                "right": {
                    "joint_angles": right_angles,
                    "end_effector": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    "coordinate_frame": "base_link",
                    "status": "idle",
                },
            }
        }

        # Merge with existing status data
        robot_id = "robot_001"
        existing = self._status_service.get_latest(robot_id) or {}
        merged = {**existing, **arm_data}

        self._runtime.call_async_in_loop(
            self._status_service.push_status(robot_id, merged)
        )
```

- [ ] **Step 2: Update factory.py to create JointStateListener**

In `robot_control/backend/app/ros2/factory.py`, add import and create the component:

Add this import at the top (after the existing topic_listener import block):

```python
from app.ros2.joint_state_listener import (
    MockJointStateListener,
    RealJointStateListener,
    JointStateListenerBase,
)
```

Add `joint_state_listener: JointStateListenerBase` to the `Ros2Components` dataclass:

```python
@dataclass
class Ros2Components:
    service_client: Ros2ServiceClientBase
    log_collector: Ros2LogCollectorBase
    topic_listener: Ros2TopicListenerBase
    joint_state_listener: JointStateListenerBase
    moveit_client: object | None  # MoveItServiceClientBase, added in Task 5
    runtime: object | None
```

In the `create_ros2_components` function, for real mode, add:

```python
joint_state_listener=RealJointStateListener(runtime),
```

For mock mode, add:

```python
joint_state_listener=MockJointStateListener(),
moveit_client=None,
```

The full real-mode block becomes:

```python
components = Ros2Components(
    runtime=runtime,
    service_client=RealRos2ServiceClient(
        runtime, timeout=settings.ros2_service_timeout
    ),
    log_collector=RealRos2LogCollector(runtime),
    topic_listener=RealRos2TopicListener(runtime),
    joint_state_listener=RealJointStateListener(runtime),
    moveit_client=None,  # created separately in Task 5
)
```

The full mock-mode block becomes:

```python
components = Ros2Components(
    runtime=None,
    service_client=MockRos2ServiceClient(),
    log_collector=MockRos2LogCollector(),
    topic_listener=MockRos2TopicListener(),
    joint_state_listener=MockJointStateListener(),
    moveit_client=None,
)
```

- [ ] **Step 3: Update main.py to start/stop JointStateListener**

In `robot_control/backend/app/main.py`, in the `lifespan` function, after the existing `await components.topic_listener.start(status_service)` line, add:

```python
        await components.joint_state_listener.start(status_service)
```

In the shutdown block, before `components.runtime.stop()`, add:

```python
        await components.joint_state_listener.stop()
```

- [ ] **Step 4: Commit**

```bash
git add robot_control/backend/app/ros2/joint_state_listener.py robot_control/backend/app/ros2/factory.py robot_control/backend/app/main.py
git commit -m "feat: add JointStateListener for arm status monitoring"
```

---

## Task 5: Add MoveIt Service Client to Backend

**Files:**
- Create: `robot_control/backend/app/ros2/moveit_client.py`
- Modify: `robot_control/backend/app/ros2/factory.py`
- Modify: `robot_control/backend/app/services/arm_service.py`
- Modify: `robot_control/backend/app/main.py`

This creates a typed ROS2 service client that calls `control_interfaces/srv/MoveP` and `control_interfaces/srv/MoveL` directly, bypassing the GenericCommand pattern.

**Prerequisite**: The `control_interfaces` Python package must be available in `ros2_libs`. After building the ros2_ws workspace, copy the install output:

```bash
# Build workspace first (from ros2_ws/)
colcon build --packages-select control_interfaces
# Copy Python bindings to backend
cp -r ros2_ws/install/control_interfaces/local/lib/python3.10/dist-packages/control_interfaces* \
      robot_control/backend/ros2_libs/local/lib/python3.10/dist-packages/
# Copy shared libraries
cp ros2_ws/install/control_interfaces/lib/*.so robot_control/backend/ros2_libs/lib/
```

- [ ] **Step 1: Create moveit_client.py**

Create `robot_control/backend/app/ros2/moveit_client.py`:

```python
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

try:
    import rclpy
    from rclpy.node import Node

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class MoveItServiceClientBase(ABC):
    @abstractmethod
    async def move_p(self, lor: str, target_pose: dict, to_frame: str,
                     reference_frame: str, planner: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def move_l(self, lor: str, waypoints: list[dict]) -> dict[str, Any]:
        ...


class MockMoveItServiceClient(MoveItServiceClientBase):
    async def move_p(self, lor: str, target_pose: dict, to_frame: str,
                     reference_frame: str, planner: str) -> dict[str, Any]:
        return {"success": True, "message": "mock: MoveP ok"}

    async def move_l(self, lor: str, waypoints: list[dict]) -> dict[str, Any]:
        return {"success": True, "message": "mock: MoveL ok"}


class RealMoveItServiceClient(MoveItServiceClientBase):
    """Direct ROS2 service client for MoveIt move_pose and move_line.

    Services:
      /move_pose  (control_interfaces/srv/MoveP)
      /move_line  (control_interfaces/srv/MoveL)
    """

    def __init__(self, runtime, timeout: float = 30.0):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed")
        self._runtime = runtime
        self._timeout = timeout
        self._clients: dict[str, Any] = {}

    def _get_or_create_client(self, service_name: str, srv_type):
        if service_name not in self._clients:
            node: Node = self._runtime.node
            client = node.create_client(srv_type, service_name)
            self._clients[service_name] = client
        return self._clients[service_name]

    async def move_p(self, lor: str, target_pose: dict, to_frame: str,
                     reference_frame: str, planner: str) -> dict[str, Any]:
        from control_interfaces.srv import MoveP
        from geometry_msgs.msg import PoseStamped

        client = self._get_or_create_client("move_pose", MoveP)

        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("MoveP service not available after 5s")
            return {"success": False, "message": "MoveP service not available"}

        req = MoveP.Request()
        req.lor = lor
        req.to_frame = to_frame
        req.reference_frame = reference_frame
        req.planner = planner

        pose = PoseStamped()
        pose.header.frame_id = target_pose.get("frame_id", reference_frame)
        pose.pose.position.x = target_pose.get("x", 0.0)
        pose.pose.position.y = target_pose.get("y", 0.0)
        pose.pose.position.z = target_pose.get("z", 0.0)
        pose.pose.orientation.x = target_pose.get("qx", 0.0)
        pose.pose.orientation.y = target_pose.get("qy", 0.0)
        pose.pose.orientation.z = target_pose.get("qz", 0.0)
        pose.pose.orientation.w = target_pose.get("qw", 1.0)
        req.target_pose = pose

        ros_future = client.call_async(req)
        return await self._bridge_future(ros_future)

    async def move_l(self, lor: str, waypoints: list[dict]) -> dict[str, Any]:
        from control_interfaces.srv import MoveL
        from geometry_msgs.msg import Pose

        client = self._get_or_create_client("move_line", MoveL)

        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("MoveL service not available after 5s")
            return {"success": False, "message": "MoveL service not available"}

        req = MoveL.Request()
        req.lor = lor

        for wp_dict in waypoints:
            pose = Pose()
            pose.position.x = wp_dict.get("x", 0.0)
            pose.position.y = wp_dict.get("y", 0.0)
            pose.position.z = wp_dict.get("z", 0.0)
            pose.orientation.x = wp_dict.get("qx", 0.0)
            pose.orientation.y = wp_dict.get("qy", 0.0)
            pose.orientation.z = wp_dict.get("qz", 0.0)
            pose.orientation.w = wp_dict.get("qw", 1.0)
            req.waypoints.append(pose)

        ros_future = client.call_async(req)
        return await self._bridge_future(ros_future)

    async def _bridge_future(self, ros_future) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        aio_future = loop.create_future()

        def _done_callback(fut):
            if aio_future.done():
                return
            try:
                response = fut.result()
                result = {
                    "success": response.success,
                    "message": getattr(response, "message", ""),
                }
                loop.call_soon_threadsafe(aio_future.set_result, result)
            except Exception as exc:
                loop.call_soon_threadsafe(aio_future.set_exception, exc)

        ros_future.add_done_callback(_done_callback)

        try:
            return await asyncio.wait_for(aio_future, timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.error("MoveIt service call timed out after %.1fs", self._timeout)
            return {"success": False, "message": f"Service call timed out after {self._timeout}s"}
```

- [ ] **Step 2: Update factory.py to create MoveItServiceClient**

In `robot_control/backend/app/ros2/factory.py`, add import:

```python
from app.ros2.moveit_client import (
    MockMoveItServiceClient,
    RealMoveItServiceClient,
    MoveItServiceClientBase,
)
```

In the `Ros2Components` dataclass, update the `moveit_client` field type:

```python
    moveit_client: MoveItServiceClientBase | None
```

In the real-mode block, add:

```python
moveit_client=RealMoveItServiceClient(runtime, timeout=settings.ros2_service_timeout),
```

In the mock-mode block, change:

```python
moveit_client=MockMoveItServiceClient(),
```

- [ ] **Step 3: Update arm_service.py to use MoveItServiceClient for movep/moveL**

In `robot_control/backend/app/services/arm_service.py`, update `ArmService.__init__` and `arm_move`:

Change the import block to add:

```python
from app.ros2.moveit_client import MoveItServiceClientBase
```

Update `__init__`:

```python
class ArmService:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None,
                 moveit_client: MoveItServiceClientBase | None = None,
                 teach_dir: str = "data/teach"):
        self._ros2 = ros2_client or MockRos2ServiceClient()
        self._moveit = moveit_client
        self._teach_dir = Path(teach_dir)
```

Replace `arm_move` method:

```python
    async def arm_move(self, robot_id: str, cmd: ArmMoveCommand) -> ApiResponse:
        if cmd.method.value == "movep" and self._moveit:
            to_frame = f"ARM-{'L' if cmd.arm.value == 'left' else 'R'}-J7_Link"
            result = await self._moveit.move_p(
                lor=cmd.arm.value,
                target_pose=cmd.position or {},
                to_frame=to_frame,
                reference_frame=cmd.coordinate,
                planner="ompl",
            )
            if result.get("success") is False:
                return ApiResponse(code=1001, message=result.get("message", "MoveP 失败"))
            return ApiResponse(data=result)

        if cmd.method.value == "moveL" and self._moveit:
            result = await self._moveit.move_l(
                lor=cmd.arm.value,
                waypoints=[cmd.position] if cmd.position else [],
            )
            if result.get("success") is False:
                return ApiResponse(code=1001, message=result.get("message", "MoveL 失败"))
            return ApiResponse(data=result)

        # Fallback to GenericCommand for moveJ and other methods
        result = await self._ros2.call_service("/ArmMoveCommand", cmd.model_dump())
        if result.get("success") is False:
            return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
        return ApiResponse(data=result)
```

- [ ] **Step 4: Update arm API endpoint to pass moveit_client**

In `robot_control/backend/app/api/arm.py`, update `_get_arm_service`:

```python
def _get_arm_service(request: Request) -> ArmService:
    settings = get_settings()
    moveit_client = getattr(request.app.state.ros2, 'moveit_client', None)
    return ArmService(
        ros2_client=request.app.state.ros2.service_client,
        moveit_client=moveit_client,
        teach_dir=settings.teach_data_dir,
    )
```

- [ ] **Step 5: Commit**

```bash
git add robot_control/backend/app/ros2/moveit_client.py robot_control/backend/app/ros2/factory.py robot_control/backend/app/services/arm_service.py robot_control/backend/app/api/arm.py
git commit -m "feat: add MoveIt service client for direct MoveP/MoveL calls"
```

---

## Task 6: Add Launch File Management to ROS2 Node Manager

**Files:**
- Modify: `robot_control/backend/app/services/ros2_manager.py`
- Modify: `robot_control/backend/app/api/ros2_nodes.py`

The backend needs to start/stop ROS2 launch files as managed units. This uses subprocess management.

- [ ] **Step 1: Add launch management to Ros2Manager**

In `robot_control/backend/app/services/ros2_manager.py`, replace the entire file with:

```python
import asyncio
import logging
import os
import signal
from pathlib import Path

from furance_shared.protocol.http_schema import ApiResponse

logger = logging.getLogger(__name__)

# Launch file definitions: name -> (package, launch_file, default_args)
LAUNCH_FILES = {
    "t1_moveit": {
        "package": "t1_moveit_config",
        "launch_file": "t1_moveit_headless.launch.py",
        "default_args": {"use_sim": "true"},
        "description": "T1 MoveIt (headless)",
    },
}


def _check_result(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
    return ApiResponse(data=result)


class LaunchProcessManager:
    """Manages launch file subprocesses."""

    def __init__(self):
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def start_launch(self, name: str) -> bool:
        if name in self._processes and self._processes[name].returncode is None:
            logger.warning("Launch %s is already running", name)
            return True

        config = LAUNCH_FILES.get(name)
        if not config:
            logger.error("Unknown launch: %s", name)
            return False

        cmd = [
            "ros2", "launch",
            config["package"],
            config["launch_file"],
        ]
        for k, v in config.get("default_args", {}).items():
            cmd.append(f"{k}:={v}")

        try:
            env = os.environ.copy()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._processes[name] = proc
            logger.info("Started launch %s (pid=%d)", name, proc.pid)
            return True
        except Exception:
            logger.exception("Failed to start launch %s", name)
            return False

    async def stop_launch(self, name: str) -> bool:
        proc = self._processes.get(name)
        if proc is None or proc.returncode is not None:
            logger.warning("Launch %s is not running", name)
            return True

        try:
            proc.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(proc.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            del self._processes[name]
            logger.info("Stopped launch %s", name)
            return True
        except Exception:
            logger.exception("Failed to stop launch %s", name)
            return False

    def is_running(self, name: str) -> bool:
        proc = self._processes.get(name)
        return proc is not None and proc.returncode is None

    def list_launches(self) -> list[dict]:
        result = []
        for name, config in LAUNCH_FILES.items():
            result.append({
                "name": name,
                "description": config["description"],
                "package": config["package"],
                "status": "running" if self.is_running(name) else "stopped",
            })
        return result


class Ros2Manager:
    def __init__(self, ros2_client=None, launch_manager: LaunchProcessManager | None = None):
        self._ros2 = ros2_client
        self._launch_manager = launch_manager or LaunchProcessManager()

    async def list_nodes(self) -> ApiResponse:
        result = await self._ros2.call_service("/GetNodeList", {})
        return _check_result(result)

    async def start_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStart", {"name": node_name})
        return _check_result(result)

    async def stop_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStop", {"name": node_name})
        return _check_result(result)

    async def node_status(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStatus", {"name": node_name})
        return _check_result(result)

    # Launch file management
    async def list_launches(self) -> ApiResponse:
        return ApiResponse(data=self._launch_manager.list_launches())

    async def start_launch(self, name: str) -> ApiResponse:
        success = await self._launch_manager.start_launch(name)
        if not success:
            return ApiResponse(code=2001, message=f"Failed to start launch: {name}")
        return ApiResponse(data={"name": name, "status": "running"})

    async def stop_launch(self, name: str) -> ApiResponse:
        success = await self._launch_manager.stop_launch(name)
        if not success:
            return ApiResponse(code=2001, message=f"Failed to stop launch: {name}")
        return ApiResponse(data={"name": name, "status": "stopped"})

    async def launch_status(self, name: str) -> ApiResponse:
        return ApiResponse(data={
            "name": name,
            "status": "running" if self._launch_manager.is_running(name) else "stopped",
        })
```

- [ ] **Step 2: Update ros2_nodes API to add launch endpoints**

In `robot_control/backend/app/api/ros2_nodes.py`, replace the entire file with:

```python
from fastapi import APIRouter, Request
from furance_shared.protocol.http_schema import ApiResponse
from app.services.ros2_manager import Ros2Manager

router = APIRouter(prefix="/api/v1/ros2", tags=["ros2"])


def _get_manager(request: Request) -> Ros2Manager:
    return Ros2Manager(
        ros2_client=request.app.state.ros2.service_client,
        launch_manager=request.app.state.launch_manager,
    )


# Node management
@router.get("/nodes", response_model=ApiResponse)
async def list_nodes(request: Request):
    manager = _get_manager(request)
    return await manager.list_nodes()


@router.post("/nodes/{node_name}/start", response_model=ApiResponse)
async def start_node(node_name: str, request: Request):
    manager = _get_manager(request)
    return await manager.start_node(node_name)


@router.post("/nodes/{node_name}/stop", response_model=ApiResponse)
async def stop_node(node_name: str, request: Request):
    manager = _get_manager(request)
    return await manager.stop_node(node_name)


@router.get("/nodes/{node_name}/status", response_model=ApiResponse)
async def node_status(node_name: str, request: Request):
    manager = _get_manager(request)
    return await manager.node_status(node_name)


# Launch file management
@router.get("/launches", response_model=ApiResponse)
async def list_launches(request: Request):
    manager = _get_manager(request)
    return await manager.list_launches()


@router.post("/launches/{name}/start", response_model=ApiResponse)
async def start_launch(name: str, request: Request):
    manager = _get_manager(request)
    return await manager.start_launch(name)


@router.post("/launches/{name}/stop", response_model=ApiResponse)
async def stop_launch(name: str, request: Request):
    manager = _get_manager(request)
    return await manager.stop_launch(name)


@router.get("/launches/{name}/status", response_model=ApiResponse)
async def launch_status(name: str, request: Request):
    manager = _get_manager(request)
    return await manager.launch_status(name)
```

- [ ] **Step 3: Update main.py to create LaunchProcessManager**

In `robot_control/backend/app/main.py`, add import:

```python
from app.services.ros2_manager import LaunchProcessManager
```

In the `lifespan` function, after `log_service = LogService()`, add:

```python
    launch_manager = LaunchProcessManager()
```

In the app.state assignments, add:

```python
    app.state.launch_manager = launch_manager
```

- [ ] **Step 4: Update frontend Ros2Nodes.vue to show launches**

In `robot_control/frontend/src/views/Ros2Nodes.vue`, add a second card below the nodes table for launch management. After the closing `</el-row>` of the first `el-col`, add a new section:

```vue
      <el-col :span="24" style="margin-top: 20px">
        <el-card class="tech-card">
          <template #header>
            <div class="tech-card-header">
              <el-icon><Cpu /></el-icon>
              <span style="margin-left: 8px">Launch文件管理</span>
              <el-button @click="refreshLaunches" style="margin-left: auto">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>

          <el-table :data="launches" border style="width: 100%">
            <el-table-column prop="name" label="Launch名称" />
            <el-table-column prop="description" label="描述" />
            <el-table-column prop="package" label="包" width="180" />
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="row.status === 'running' ? 'success' : 'info'">
                  {{ row.status === 'running' ? '运行中' : '停止' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button
                  v-if="row.status !== 'running'"
                  type="success"
                  size="small"
                  @click="handleStartLaunch(row.name)"
                >
                  <el-icon><VideoPlay /></el-icon>
                  启动
                </el-button>
                <el-button
                  v-else
                  type="danger"
                  size="small"
                  @click="handleStopLaunch(row.name)"
                >
                  <el-icon><SwitchButton /></el-icon>
                  停止
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
```

In the `<script setup>` section, add:

```javascript
const launches = ref([])

async function refreshLaunches() {
  try {
    const response = await ros2Api.listLaunches()
    const payload = response.data
    launches.value = payload?.data || payload || []
  } catch (error) {
    ElMessage.error(error.message || '获取Launch列表失败')
  }
}

async function handleStartLaunch(name) {
  try {
    await ros2Api.startLaunch(name)
    ElMessage.success(`Launch ${name} 启动指令已发送`)
    refreshLaunches()
  } catch (error) {
    ElMessage.error(error.message || '启动Launch失败')
  }
}

async function handleStopLaunch(name) {
  try {
    await ros2Api.stopLaunch(name)
    ElMessage.success(`Launch ${name} 停止指令已发送`)
    refreshLaunches()
  } catch (error) {
    ElMessage.error(error.message || '停止Launch失败')
  }
}

onMounted(refreshLaunches)
```

- [ ] **Step 5: Update frontend ros2 API client**

In `robot_control/frontend/src/api/ros2.js`, add launch API methods:

```javascript
import api from '.'

export const ros2Api = {
  listNodes: () => api.get('/ros2/nodes'),
  startNode: (name) => api.post(`/ros2/nodes/${name}/start`),
  stopNode: (name) => api.post(`/ros2/nodes/${name}/stop`),
  nodeStatus: (name) => api.get(`/ros2/nodes/${name}/status`),

  listLaunches: () => api.get('/ros2/launches'),
  startLaunch: (name) => api.post(`/ros2/launches/${name}/start`),
  stopLaunch: (name) => api.post(`/ros2/launches/${name}/stop`),
  launchStatus: (name) => api.get(`/ros2/launches/${name}/status`),
}
```

- [ ] **Step 6: Commit**

```bash
git add robot_control/backend/app/services/ros2_manager.py robot_control/backend/app/api/ros2_nodes.py robot_control/backend/app/main.py robot_control/frontend/src/views/Ros2Nodes.vue robot_control/frontend/src/api/ros2.js
git commit -m "feat: add launch file management to ROS2 node manager"
```

---

## Task 7: Copy control_interfaces to ros2_libs

**Files:**
- Modify: `robot_control/backend/ros2_libs/` (add control_interfaces Python packages and .so files)

This is a build/ops step, not code. After the ros2_ws is built with the t1_robot packages, copy the control_interfaces Python bindings to the backend's ros2_libs directory so the `RealMoveItServiceClient` can import them.

- [ ] **Step 1: Build the ros2_ws workspace**

```bash
cd /home/kty/Desktop/furance_robot/ros2_ws
# Remove COLCON_IGNORE temporarily if present
mv install/COLCON_IGNORE install/COLCON_IGNORE.bak 2>/dev/null || true
colcon build --packages-select control_interfaces
mv install/COLCON_IGNORE.bak install/COLCON_IGNORE 2>/dev/null || true
```

- [ ] **Step 2: Copy control_interfaces Python bindings to ros2_libs**

```bash
# Copy Python packages
cp -r /home/kty/Desktop/furance_robot/ros2_ws/install/control_interfaces/local/lib/python3.10/dist-packages/control_interfaces* \
      /home/kty/Desktop/furance_robot/robot_control/backend/ros2_libs/local/lib/python3.10/dist-packages/

# Copy shared libraries
cp /home/kty/Desktop/furance_robot/ros2_ws/install/control_interfaces/lib/*.so \
   /home/kty/Desktop/furance_robot/robot_control/backend/ros2_libs/lib/
```

- [ ] **Step 3: Verify import works**

```bash
cd /home/kty/Desktop/furance_robot/robot_control/backend
PYTHONPATH=ros2_libs/local/lib/python3.10/dist-packages:$PYTHONPATH \
LD_LIBRARY_PATH=ros2_libs/lib:$LD_LIBRARY_PATH \
python3 -c "from control_interfaces.srv import MoveP, MoveL; print('OK')"
```

Expected output: `OK`

---

## Self-Review Checklist

**1. Spec coverage:**
- python_pkgs dependencies → Task 1 ✓
- t1_moveit_launch.py (headless) → Task 2 ✓
- RViz launch → Task 3 ✓
- Status monitoring data source → Task 4 ✓
- MoveP/MoveL interface → Task 5 ✓
- Launch management integration → Task 6 ✓
- control_interfaces availability → Task 7 ✓

**2. Placeholder scan:** No TBD, TODO, or "implement later" found. All code blocks are complete.

**3. Type consistency:**
- `MoveItServiceClientBase` used consistently in factory.py and arm_service.py
- `LaunchProcessManager` used consistently in ros2_manager.py, api, and main.py
- API endpoints: `/ros2/launches` prefix matches across backend and frontend
- `ArmMoveCommand.method.value` checked as "movep" and "moveL" (matching ArmMoveMethod enum)

# T1 MoveIt Integration Design

## Overview

Integrate T1 robot's MoveIt configuration with the robot_control backend system. Five work items: fix python_pkgs dependencies, create headless MoveIt launch, create standalone RViz launch, connect status monitoring to /joint_states, and implement MoveP/MoveL via direct ROS2 service calls.

---

## 1. python_pkgs Dependencies

**Problem**: `package.xml` only declares ament_cmake and ament_python. The code imports from many undeclared packages.

**Solution**: Add all missing `<exec_depend>` entries based on actual imports:

- `rclpy` — core ROS2 Python client
- `sensor_msgs` — JointState message
- `trajectory_msgs` — JointTrajectoryPoint
- `control_msgs` — FollowJointTrajectory action
- `control_interfaces` — MoveP, MoveL, MoveJ srv types
- `geometry_msgs` — PoseStamped, Pose
- `interface_pkg` — MotFeedback, Robotstatus, MoveToJointPositions etc.
- `joint_state_publisher` — JointStatePublisher class (used by GUI)
- `python_qt_binding` — Qt bindings (used by GUI)
- `std_msgs` — String message
- `tf2_ros` — TransformListener (if needed by any module)

**Files changed**: `ros2_ws/src/t1_robot/python_pkgs/package.xml`

Also add `install_requires` entries in `setup.py` for the same.

---

## 2. t1_moveit_launch.py (Headless)

**Problem**: Existing `t1_moveit.launch.py` includes RViz and joint_state_publisher_gui which require display. The backend runs headless on Ubuntu IPC.

**Solution**: Create `t1_moveit.launch.py` that launches only headless nodes:

Nodes to include:
1. `robot_state_publisher` — publishes TF from URDF
2. `move_group` — MoveIt planning & execution
3. `joint_states_bridge` (python_pkgs/t1_joint_state_bridge) — bridges motor feedback/sim commands to /joint_states
4. `sim_arm_controller` or `moveit_arm_controller` — trajectory action server (controlled by `use_sim` arg)
5. `t1_moveit_server` — C++ service node (move_pose, move_line, execute_trajectory)
6. `target_model` + `target_base_tf` — target visualization (optional, can be disabled)

Nodes explicitly excluded:
- `rviz2` — no display available
- `service_control_gui` (t1_joint_state_publisher_gui) — requires Qt/display

**Launch arguments**:
- `use_sim` (default: "true") — use sim_arm_controller vs real controller
- `description_package` (default: "t1_moveit_config")
- `use_sim_time` (default: "false")

**Backend integration**: The backend's `Ros2Manager` will manage this launch file as a single unit:
- Start: `ros2 launch t1_moveit_config t1_moveit.launch.py use_sim:=true`
- Stop: Send SIGTERM to the launch process
- Status: Check if the process is running

**Files**:
- New: `ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_moveit.launch.py`
- Modified: `robot_control/backend/app/services/ros2_manager.py` — add launch file management

---

## 3. RViz Launch (Standalone Debug)

**Purpose**: For manual debugging only — visualize robot joint angles when controlling from web UI.

**Not integrated** with backend node management. Started manually by developer.

**Solution**: Create `t1_rviz.launch.py` that starts:
1. `rviz2` with MoveIt config (`moveit.rviz`)

This assumes the MoveIt launch is already running (providing move_group, robot_state_publisher, etc.).

**Files**:
- New: `ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_rviz.launch.py`

---

## 4. Status Monitoring Data Source

**Problem**: Dashboard shows arm joint_angles and end_effector, but data comes from `/robot_status` topic which currently doesn't include T1-specific arm data.

**Solution**: Add a new `JointStateListener` in the backend that subscribes to `/joint_states` (sensor_msgs/JointState) and extracts:

- Left arm joints: `ARM-L-J1_Joint` through `ARM-L-J7_Joint`
- Right arm joints: `ARM-R-J1_Joint` through `ARM-R-J7_Joint`
- End effector pose: computed from TF (lookup transform from base_link to ARM-L-J7_Link / ARM-R-J7_Link)

This listener pushes arm data to `StatusService.push_status()`, merging with the existing `/robot_status` data.

**Data flow**:
```
/joint_states (sensor_msgs/JointState)
    → JointStateListener (backend ROS2 node)
        → extract left/right joint angles
        → lookup TF for end-effector pose
        → StatusService.push_status(robot_id, {arm: {left: {...}, right: {...}}})
            → WebSocket → Dashboard
```

**Implementation**:
- New class `RealJointStateListener` (parallel to `RealRos2TopicListener`)
- Subscribes to `/joint_states`
- Subscribes to `/tf` and `/tf_static` for end-effector pose lookup
- Pushes to StatusService, merging with existing `/robot_status` data
- Mock implementation returns zero values

**Files**:
- Modified: `robot_control/backend/app/ros2/topic_listener.py` — add JointStateListener
- Modified: `robot_control/backend/app/ros2/factory.py` — create JointStateListener
- Modified: `robot_control/backend/app/main.py` — start/stop JointStateListener

**Frontend**: No changes needed — Dashboard already reads `arm.left/right.joint_angles` and `arm.left/right.end_effector` from status data.

---

## 5. MoveP and MoveL Interface

**Problem**: `ArmService.arm_move()` sends `/ArmMoveCommand` via GenericCommand, but t1_moveit_server exposes specific ROS2 services: `move_pose` (MoveP.srv) and `move_line` (MoveL.srv).

**Solution**: Create a `MoveItServiceClient` that directly calls `control_interfaces/srv/MoveP` and `control_interfaces/srv/MoveL`.

**Implementation**:

```python
class MoveItServiceClientBase(ABC):
    async def move_p(self, lor, target_pose, to_frame, reference_frame, planner) -> dict
    async def move_l(self, lor, waypoints) -> dict
    async def move_j(self, lor, joint_positions) -> dict

class MockMoveItServiceClient(MoveItServiceClientBase):
    # Returns success=True for mock mode

class RealMoveItServiceClient(MoveItServiceClientBase):
    # Uses Ros2Runtime to create typed service clients for:
    #   /move_pose (control_interfaces/srv/MoveP)
    #   /move_line (control_interfaces/srv/MoveL)
```

**ArmService changes**:
- `arm_move()` dispatches based on `method`:
  - `movep` → `MoveItServiceClient.move_p()`
  - `moveL` → `MoveItServiceClient.move_l()`
  - `moveJ` → stays with GenericCommand or uses a new move_j service (TBD)

**Data mapping** (ArmMoveCommand → MoveP srv):
- `arm` → `lor` ("left"/"right")
- `position` {x,y,z,roll,pitch,yaw} → `target_pose` (geometry_msgs/PoseStamped)
- `coordinate` → `reference_frame`
- `to_frame` → default to "ARM-L-J7_Link" or "ARM-R-J7_Link" based on arm side

**Data mapping** (ArmMoveCommand → MoveL srv):
- `arm` → `lor`
- `position` → single waypoint in `waypoints` list

**Prerequisite**: `control_interfaces` Python package must be in `ros2_libs`. This requires building the workspace and copying the install output.

**Files**:
- New: `robot_control/backend/app/ros2/moveit_client.py`
- Modified: `robot_control/backend/app/services/arm_service.py` — use MoveItServiceClient
- Modified: `robot_control/backend/app/ros2/factory.py` — create MoveItServiceClient
- Modified: `robot_control/backend/app/main.py` — store on app.state

---

## Dependencies & Build Order

1. Build `ros2_ws` workspace (colcon build) to ensure all packages are available
2. Copy `control_interfaces` Python packages to `robot_control/backend/ros2_libs/`
3. Implement changes in order:
   - python_pkgs package.xml (independent)
   - t1_moveit.launch.py (independent)
   - t1_rviz.launch.py (independent)
   - JointStateListener (backend change)
   - MoveIt client + arm service refactor (backend change, depends on control_interfaces being available)

## Testing

- python_pkgs: `colcon build` succeeds after dependency fix
- Launch file: `ros2 launch t1_moveit_config t1_moveit.launch.py use_sim:=true` starts without display errors
- RViz launch: `ros2 launch t1_moveit_config t1_rviz.launch.py` opens RViz with robot model
- Status monitoring: Dashboard shows live joint angles when MoveIt launch is running
- MoveP/MoveL: arm control API returns success when MoveIt is running

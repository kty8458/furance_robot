import asyncio
import logging
import math
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

try:
    from rclpy.node import Node
    from rclpy.task import Future

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


LEFT_JOINT_NAMES = [f"ARM-L-J{i}_Joint" for i in range(1, 8)]
RIGHT_JOINT_NAMES = [f"ARM-R-J{i}_Joint" for i in range(1, 8)]


def _rpy_deg_to_quat(roll_deg: float, pitch_deg: float, yaw_deg: float) -> tuple[float, float, float, float]:
    """XYZ intrinsic RPY (degrees) -> quaternion (qx, qy, qz, qw)."""
    r = math.radians(roll_deg) * 0.5
    p = math.radians(pitch_deg) * 0.5
    y = math.radians(yaw_deg) * 0.5
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    qw = cr * cp * cy + sr * sp * sy
    qx = sr * cp * cy - cr * sp * sy
    qy = cr * sp * cy + sr * cp * sy
    qz = cr * cp * sy - sr * sp * cy
    return qx, qy, qz, qw


def _pose_dict_to_xyz_quat(pose: dict) -> tuple[float, float, float, float, float, float, float]:
    """Frontend pose dict {x, y, z, roll, pitch, yaw} (mm + deg) or {x, y, z, qx, qy, qz, qw} (m)
    -> (x, y, z, qx, qy, qz, qw) in meters / quaternion.

    Heuristic: if any of qx/qy/qz/qw is supplied we treat as meters + quaternion;
    otherwise we treat as mm + RPY degrees (the frontend / teach-point format).
    """
    has_quat = any(k in pose for k in ("qx", "qy", "qz", "qw"))
    if has_quat:
        return (
            float(pose.get("x", 0.0)),
            float(pose.get("y", 0.0)),
            float(pose.get("z", 0.0)),
            float(pose.get("qx", 0.0)),
            float(pose.get("qy", 0.0)),
            float(pose.get("qz", 0.0)),
            float(pose.get("qw", 1.0)),
        )
    x_m = float(pose.get("x", 0.0)) / 1000.0
    y_m = float(pose.get("y", 0.0)) / 1000.0
    z_m = float(pose.get("z", 0.0)) / 1000.0
    qx, qy, qz, qw = _rpy_deg_to_quat(
        float(pose.get("roll", 0.0)),
        float(pose.get("pitch", 0.0)),
        float(pose.get("yaw", 0.0)),
    )
    return x_m, y_m, z_m, qx, qy, qz, qw


class MoveItServiceClientBase(ABC):
    @abstractmethod
    async def move_p(self, lor: str, target_pose: dict, to_frame: str,
                     reference_frame: str, planner: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def move_l(self, lor: str, waypoints: list[dict]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def move_j(self, lor: str, joint_positions: list[float],
                     duration: float = 3.0) -> dict[str, Any]:
        ...

    @abstractmethod
    async def move_j_both(self, left_joint_positions: list[float],
                          right_joint_positions: list[float],
                          duration: float = 3.0) -> dict[str, Any]:
        ...


class MockMoveItServiceClient(MoveItServiceClientBase):
    async def move_p(self, lor: str, target_pose: dict, to_frame: str,
                     reference_frame: str, planner: str) -> dict[str, Any]:
        return {"success": True, "message": "mock: MoveP ok"}

    async def move_l(self, lor: str, waypoints: list[dict]) -> dict[str, Any]:
        return {"success": True, "message": "mock: MoveL ok"}

    async def move_j(self, lor: str, joint_positions: list[float],
                     duration: float = 3.0) -> dict[str, Any]:
        if len(joint_positions) != 7:
            return {"success": False, "message": "moveJ requires 7 joint angles"}
        return {"success": True, "message": "mock: MoveJ ok"}

    async def move_j_both(self, left_joint_positions: list[float],
                          right_joint_positions: list[float],
                          duration: float = 3.0) -> dict[str, Any]:
        return {"success": True, "message": "mock: MoveJ both ok"}


class RealMoveItServiceClient(MoveItServiceClientBase):
    """Direct ROS2 service client for MoveIt move_pose / move_line / execute_trajectory.

    Services:
      /move_pose           (control_interfaces/srv/MoveP)   -> move_p
      /move_line           (control_interfaces/srv/MoveL)   -> move_l
      /execute_trajectory  (control_interfaces/srv/ExecuteTrajectory) -> move_j
    """

    def __init__(self, runtime, timeout: float = 30.0):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed")
        self._runtime = runtime
        self._timeout = timeout
        self._clients: dict[str, Any] = {}
        # Cache of latest /joint_states by joint name (radians). Populated lazily
        # the first time move_j needs a trajectory start point.
        self._joint_positions: dict[str, float] = {}
        self._joint_state_sub = None

    def _ensure_joint_state_sub(self):
        if self._joint_state_sub is not None:
            return
        from sensor_msgs.msg import JointState

        def _cb(msg):
            for i, name in enumerate(msg.name):
                if i < len(msg.position):
                    self._joint_positions[name] = float(msg.position[i])

        self._joint_state_sub = self._runtime.node.create_subscription(
            JointState, "/joint_states", _cb, 10,
        )
        logger.info("MoveItClient subscribed to /joint_states for trajectory start state")

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
        x, y, z, qx, qy, qz, qw = _pose_dict_to_xyz_quat(target_pose)
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = z
        pose.pose.orientation.x = qx
        pose.pose.orientation.y = qy
        pose.pose.orientation.z = qz
        pose.pose.orientation.w = qw
        req.target_pose = pose

        return await self._bridge_future(client.call_async(req))

    async def move_l(self, lor: str, waypoints: list[dict]) -> dict[str, Any]:
        from control_interfaces.srv import MoveL
        from geometry_msgs.msg import Pose

        client = self._get_or_create_client("move_line", MoveL)
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("MoveL service not available after 5s")
            return {"success": False, "message": "MoveL service not available"}

        req = MoveL.Request()
        req.lor = lor
        for wp in waypoints:
            pose = Pose()
            x, y, z, qx, qy, qz, qw = _pose_dict_to_xyz_quat(wp)
            pose.position.x = x
            pose.position.y = y
            pose.position.z = z
            pose.orientation.x = qx
            pose.orientation.y = qy
            pose.orientation.z = qz
            pose.orientation.w = qw
            req.waypoints.append(pose)

        return await self._bridge_future(client.call_async(req))

    async def move_j(self, lor: str, joint_positions: list[float],
                     duration: float = 3.0) -> dict[str, Any]:
        """Send a JointTrajectory (current state → target) to /execute_trajectory.

        MoveIt's trajectory_execution_manager validates that the trajectory's
        start point matches the current robot state within
        ``allowed_start_tolerance`` (default 0.05 rad). We therefore prepend a
        zero-time start waypoint taken from the latest /joint_states reading.

        The C++ server picks left/right MoveGroup based on the first joint name
        prefix (ARM-L / ARM-R), so we use the proper joint names per side.
        """
        from control_interfaces.srv import ExecuteTrajectory
        from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
        from builtin_interfaces.msg import Duration

        if len(joint_positions) != 7:
            return {"success": False, "message": "moveJ requires 7 joint angles"}

        client = self._get_or_create_client("execute_trajectory", ExecuteTrajectory)
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("ExecuteTrajectory service not available after 5s")
            return {"success": False, "message": "ExecuteTrajectory service not available"}

        names = LEFT_JOINT_NAMES if lor == "left" else RIGHT_JOINT_NAMES

        # Frontend / hardware status report joint angles in degrees; MoveIt /
        # URDF expect radians.
        target_rad = [math.radians(float(p)) for p in joint_positions]

        # Resolve current joint positions to use as the trajectory start point.
        self._ensure_joint_state_sub()
        # Give the subscription a brief window to populate on first call.
        for _ in range(20):
            if all(n in self._joint_positions for n in names):
                break
            await asyncio.sleep(0.05)
        if not all(n in self._joint_positions for n in names):
            logger.error("No /joint_states received for %s", names)
            return {"success": False, "message": "Current joint state unavailable"}

        start_rad = [self._joint_positions[n] for n in names]

        # 根据实际关节角度变化自动缩放 trajectory 的 time_from_start，
        # 使 MoveIt 的 allowed_execution_duration_scaling 能给硬件足够窗口。
        # 物理臂 ~0.3 rad/s，floor 至 caller 传入的 duration，+1s 缓冲。
        max_delta = max(abs(t - s) for t, s in zip(target_rad, start_rad))
        scaled_duration = max(duration, max_delta / 0.3 + 1.0)
        logger.info("move_j max_delta=%.3f rad, scaled_duration=%.1fs", max_delta, scaled_duration)

        traj = JointTrajectory()
        traj.joint_names = names

        start_point = JointTrajectoryPoint()
        start_point.positions = start_rad
        start_dur = Duration()
        start_dur.sec = 0
        start_dur.nanosec = 0
        start_point.time_from_start = start_dur
        traj.points.append(start_point)

        end_point = JointTrajectoryPoint()
        end_point.positions = target_rad
        end_dur = Duration()
        end_dur.sec = int(scaled_duration)
        end_dur.nanosec = int((scaled_duration - int(scaled_duration)) * 1e9)
        end_point.time_from_start = end_dur
        traj.points.append(end_point)

        req = ExecuteTrajectory.Request()
        req.trajectory = traj

        return await self._bridge_future(client.call_async(req))

    async def move_j_both(self, left_joint_positions: list[float],
                          right_joint_positions: list[float],
                          duration: float = 3.0) -> dict[str, Any]:
        """Send a dual-arm JointTrajectory to /execute_trajectory.

        Combines left and right joint names (14 total) into one trajectory.
        C++ handler detects both-arm by checking joint_names for both
        ARM-L and ARM-R prefixes and routes to both_move_group_.
        """
        from control_interfaces.srv import ExecuteTrajectory
        from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
        from builtin_interfaces.msg import Duration

        if len(left_joint_positions) != 7 or len(right_joint_positions) != 7:
            return {"success": False, "message": "moveJ both requires 7+7 joint angles"}

        client = self._get_or_create_client("execute_trajectory", ExecuteTrajectory)
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("ExecuteTrajectory service not available after 5s")
            return {"success": False, "message": "ExecuteTrajectory service not available"}

        names = LEFT_JOINT_NAMES + RIGHT_JOINT_NAMES

        left_rad = [math.radians(float(p)) for p in left_joint_positions]
        right_rad = [math.radians(float(p)) for p in right_joint_positions]
        target_rad = left_rad + right_rad

        self._ensure_joint_state_sub()
        for _ in range(20):
            if all(n in self._joint_positions for n in names):
                break
            await asyncio.sleep(0.05)
        if not all(n in self._joint_positions for n in names):
            logger.error("No /joint_states received for dual-arm")
            return {"success": False, "message": "Current joint state unavailable"}

        start_rad = [self._joint_positions[n] for n in names]

        max_delta = max(abs(t - s) for t, s in zip(target_rad, start_rad))
        scaled_duration = max(duration, max_delta / 0.3 + 1.0)
        logger.info("move_j_both max_delta=%.3f rad, scaled_duration=%.1fs", max_delta, scaled_duration)

        traj = JointTrajectory()
        traj.joint_names = names

        start_point = JointTrajectoryPoint()
        start_point.positions = start_rad
        start_dur = Duration()
        start_dur.sec = 0
        start_dur.nanosec = 0
        start_point.time_from_start = start_dur
        traj.points.append(start_point)

        end_point = JointTrajectoryPoint()
        end_point.positions = target_rad
        end_dur = Duration()
        end_dur.sec = int(scaled_duration)
        end_dur.nanosec = int((scaled_duration - int(scaled_duration)) * 1e9)
        end_point.time_from_start = end_dur
        traj.points.append(end_point)

        req = ExecuteTrajectory.Request()
        req.trajectory = traj

        return await self._bridge_future(client.call_async(req))

    async def _bridge_future(self, ros_future) -> dict[str, Any]:
        loop = asyncio.get_event_loop()
        aio_future = loop.create_future()

        def _done_callback(fut):
            if aio_future.done():
                return
            try:
                response = fut.result()
                result = {
                    "success": bool(response.success),
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

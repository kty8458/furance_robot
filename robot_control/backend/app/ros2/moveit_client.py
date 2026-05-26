import asyncio
import logging
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
        pose.pose.position.x = float(target_pose.get("x", 0.0))
        pose.pose.position.y = float(target_pose.get("y", 0.0))
        pose.pose.position.z = float(target_pose.get("z", 0.0))
        pose.pose.orientation.x = float(target_pose.get("qx", 0.0))
        pose.pose.orientation.y = float(target_pose.get("qy", 0.0))
        pose.pose.orientation.z = float(target_pose.get("qz", 0.0))
        pose.pose.orientation.w = float(target_pose.get("qw", 1.0))
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
            pose.position.x = float(wp.get("x", 0.0))
            pose.position.y = float(wp.get("y", 0.0))
            pose.position.z = float(wp.get("z", 0.0))
            pose.orientation.x = float(wp.get("qx", 0.0))
            pose.orientation.y = float(wp.get("qy", 0.0))
            pose.orientation.z = float(wp.get("qz", 0.0))
            pose.orientation.w = float(wp.get("qw", 1.0))
            req.waypoints.append(pose)

        return await self._bridge_future(client.call_async(req))

    async def move_j(self, lor: str, joint_positions: list[float],
                     duration: float = 3.0) -> dict[str, Any]:
        """Send a single-waypoint JointTrajectory to /execute_trajectory.

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

        traj = JointTrajectory()
        traj.joint_names = names
        point = JointTrajectoryPoint()
        point.positions = [float(p) for p in joint_positions]
        dur = Duration()
        dur.sec = int(duration)
        dur.nanosec = int((duration - int(duration)) * 1e9)
        point.time_from_start = dur
        traj.points.append(point)

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

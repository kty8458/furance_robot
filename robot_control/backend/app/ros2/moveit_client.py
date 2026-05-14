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
            pose.pose.position.z = wp_dict.get("z", 0.0)
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
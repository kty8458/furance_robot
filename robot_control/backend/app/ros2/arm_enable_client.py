import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

try:
    from rclpy.node import Node

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class ArmEnableClientBase(ABC):
    @abstractmethod
    async def enable(self, enable: bool) -> dict[str, Any]:
        ...

    @abstractmethod
    async def clear_error(self) -> dict[str, Any]:
        ...


class MockArmEnableClient(ArmEnableClientBase):
    async def enable(self, enable: bool) -> dict[str, Any]:
        return {"success": True, "message": f"mock: {'enabled' if enable else 'disabled'}"}

    async def clear_error(self) -> dict[str, Any]:
        return {"success": True, "message": "mock: error cleared"}


class RealArmEnableClient(ArmEnableClientBase):
    """Native ROS2 clients for the arm hardware controller.

    Services:
      /robot_enable_control (interface_pkg/srv/RobotEnableControl) -> enable
      /robot_clear_error    (interface_pkg/srv/ClearError)         -> clear_error
    """

    ENABLE_SERVICE = "/robot_enable_control"
    CLEAR_ERROR_SERVICE = "/robot_clear_error"

    def __init__(self, runtime, timeout: float = 10.0):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed")
        self._runtime = runtime
        self._timeout = timeout
        self._clients: dict[str, Any] = {}

    def _get_or_create_client(self, service_name: str, srv_type):
        if service_name not in self._clients:
            node: Node = self._runtime.node
            self._clients[service_name] = node.create_client(srv_type, service_name)
        return self._clients[service_name]

    async def enable(self, enable: bool) -> dict[str, Any]:
        from interface_pkg.srv import RobotEnableControl

        client = self._get_or_create_client(self.ENABLE_SERVICE, RobotEnableControl)
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("Service %s not available after 5s", self.ENABLE_SERVICE)
            return {"success": False, "message": f"Service {self.ENABLE_SERVICE} not available"}

        req = RobotEnableControl.Request()
        req.enable = bool(enable)
        return await self._bridge_future(client.call_async(req))

    async def clear_error(self) -> dict[str, Any]:
        from interface_pkg.srv import ClearError

        client = self._get_or_create_client(self.CLEAR_ERROR_SERVICE, ClearError)
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("Service %s not available after 5s", self.CLEAR_ERROR_SERVICE)
            return {"success": False, "message": f"Service {self.CLEAR_ERROR_SERVICE} not available"}

        req = ClearError.Request()
        req.clear_error = True
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
            logger.error("Arm enable service timed out after %.1fs", self._timeout)
            return {"success": False, "message": f"Service call timed out after {self._timeout}s"}

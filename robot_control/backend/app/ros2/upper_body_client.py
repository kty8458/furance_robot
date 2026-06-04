import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

try:
    from rclpy.node import Node

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class UpperBodyClientBase(ABC):
    @abstractmethod
    async def waist_control(self, waist_angle: float, waist_speed: float) -> dict[str, Any]:
        ...

    @abstractmethod
    async def ascend_control(self, ascend_pos: float, ascend_speed: float) -> dict[str, Any]:
        ...

    @abstractmethod
    async def head_control(self, head_angle: float, head_speed: float) -> dict[str, Any]:
        ...


class MockUpperBodyClient(UpperBodyClientBase):
    async def waist_control(self, waist_angle: float, waist_speed: float) -> dict[str, Any]:
        return {"success": True, "message": f"mock: waist set to {waist_angle}"}

    async def ascend_control(self, ascend_pos: float, ascend_speed: float) -> dict[str, Any]:
        return {"success": True, "message": f"mock: ascend set to {ascend_pos}"}

    async def head_control(self, head_angle: float, head_speed: float) -> dict[str, Any]:
        return {"success": True, "message": f"mock: head set to {head_angle}"}


class RealUpperBodyClient(UpperBodyClientBase):
    """Direct ROS2 service client for waist / ascend / head control."""

    def __init__(self, runtime, timeout: float = 10.0):
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

    async def waist_control(self, waist_angle: float, waist_speed: float) -> dict[str, Any]:
        from interface_pkg.srv import WaistControl

        client = self._get_or_create_client("waist_control", WaistControl)
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("WaistControl service not available")
            return {"success": False, "message": "WaistControl service not available"}

        req = WaistControl.Request()
        req.waist_angle = float(waist_angle)
        req.waist_speed = int(waist_speed)
        req.reserve = 0
        return await self._bridge_future(client.call_async(req))

    async def ascend_control(self, ascend_pos: float, ascend_speed: float) -> dict[str, Any]:
        from interface_pkg.srv import AscendControl

        client = self._get_or_create_client("ascend_control", AscendControl)
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("AscendControl service not available")
            return {"success": False, "message": "AscendControl service not available"}

        req = AscendControl.Request()
        req.ascend_pos = float(ascend_pos)
        req.ascend_speed = int(ascend_speed)
        req.reserve = 0
        return await self._bridge_future(client.call_async(req))

    async def head_control(self, head_angle: float, head_speed: float) -> dict[str, Any]:
        from interface_pkg.srv import HeadControl

        client = self._get_or_create_client("head_control", HeadControl)
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("HeadControl service not available")
            return {"success": False, "message": "HeadControl service not available"}

        req = HeadControl.Request()
        req.head_angle = float(head_angle)
        req.head_speed = int(head_speed)
        req.reserve = 0
        return await self._bridge_future(client.call_async(req))

    async def _bridge_future(self, ros_future) -> dict[str, Any]:
        import asyncio

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
            logger.error("Upper body service call timed out after %.1fs", self._timeout)
            return {"success": False, "message": f"Service call timed out after {self._timeout}s"}

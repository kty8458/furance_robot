import asyncio
import json
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

# Try importing custom srv interface; fallback to None if unavailable
_GENERIC_SRV_TYPE = None
if HAS_RCLPY:
    try:
        from furance_interfaces.srv import GenericCommand

        _GENERIC_SRV_TYPE = GenericCommand
    except ImportError:
        logger.warning(
            "furance_interfaces.srv.GenericCommand not found. "
            "Real ROS2 service calls will not work until the package is built."
        )


class Ros2ServiceClientBase(ABC):
    @abstractmethod
    async def call_service(self, service_name: str, request: dict[str, Any]) -> dict[str, Any]:
        ...


class MockRos2ServiceClient(Ros2ServiceClientBase):
    async def call_service(self, service_name: str, request: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "message": "ok"}


class RealRos2ServiceClient(Ros2ServiceClientBase):
    """ROS2 service client using furance_interfaces/srv/GenericCommand.

    All robot services share a single srv type:
        Request:  string command, string params_json
        Response: bool success, string message, string result_json
    """

    def __init__(self, runtime, timeout: float = 30.0):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed")
        if _GENERIC_SRV_TYPE is None:
            raise RuntimeError(
                "furance_interfaces.srv.GenericCommand not available. "
                "Build the furance_interfaces package first."
            )
        self._runtime = runtime
        self._timeout = timeout
        self._clients: dict[str, Any] = {}

    def _get_or_create_client(self, service_name: str):
        """Get cached service client or create a new one."""
        if service_name not in self._clients:
            node: Node = self._runtime.node
            client = node.create_client(
                _GENERIC_SRV_TYPE,
                service_name,
            )
            self._clients[service_name] = client
        return self._clients[service_name]

    async def call_service(self, service_name: str, request: dict[str, Any]) -> dict[str, Any]:
        """Call a ROS2 service via GenericCommand interface.

        Args:
            service_name: ROS2 service name (e.g. "/HomeCommand")
            request: Dict payload to send as params_json

        Returns:
            Dict with keys: success, message, and optional result data
        """
        client = self._get_or_create_client(service_name)
        node: Node = self._runtime.node

        # Wait for service to be available
        if not client.wait_for_service(timeout_sec=5.0):
            logger.error("Service %s not available after 5s", service_name)
            return {
                "success": False,
                "message": f"Service {service_name} not available",
            }

        # Build request — extract command from service name
        command = service_name.lstrip("/")
        req = _GENERIC_SRV_TYPE.Request()
        req.command = command
        req.params_json = json.dumps(request)

        # Call service asynchronously and bridge to asyncio
        ros_future = client.call_async(req)

        # Bridge rclpy Future to asyncio via polling
        result = await self._bridge_future(ros_future)
        return result

    async def _bridge_future(self, ros_future: Future) -> dict[str, Any]:
        """Bridge rclpy Future to asyncio by polling."""
        loop = asyncio.get_event_loop()
        aio_future = loop.create_future()

        def _done_callback(fut: Future):
            if aio_future.done():
                return
            try:
                response = fut.result()
                result = {
                    "success": response.success,
                    "message": response.message,
                }
                if response.result_json:
                    try:
                        result["data"] = json.loads(response.result_json)
                    except json.JSONDecodeError:
                        result["data"] = response.result_json
                loop.call_soon_threadsafe(aio_future.set_result, result)
            except Exception as exc:
                loop.call_soon_threadsafe(aio_future.set_exception, exc)

        ros_future.add_done_callback(_done_callback)

        try:
            return await asyncio.wait_for(aio_future, timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.error("Service call timed out after %.1fs", self._timeout)
            return {"success": False, "message": f"Service call timed out after {self._timeout}s"}

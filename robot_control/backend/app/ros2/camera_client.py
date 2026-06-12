import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class CameraClientBase(ABC):
    @abstractmethod
    async def get_camera_list(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        ...

    @abstractmethod
    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        ...

    @abstractmethod
    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        ...


class MockCameraClient(CameraClientBase):
    def __init__(self):
        self._mock_cameras = [
            {"id": "head", "name": "头部相机 (Mock)", "position": "head", "connected": True, "serial": "MOCK001",
             "color_width": 1280, "color_height": 720, "color_fps": 30, "depth_width": 848, "depth_height": 480, "depth_fps": 30},
            {"id": "left_arm", "name": "左臂相机 (Mock)", "position": "left_arm", "connected": True, "serial": "MOCK002",
             "color_width": 640, "color_height": 480, "color_fps": 30, "depth_width": 640, "depth_height": 400, "depth_fps": 30},
            {"id": "right_arm", "name": "右臂相机 (Mock)", "position": "right_arm", "connected": False, "serial": "",
             "color_width": 0, "color_height": 0, "color_fps": 0, "depth_width": 0, "depth_height": 0, "depth_fps": 0},
        ]

    async def get_camera_list(self) -> dict[str, Any]:
        return {"success": True, "cameras": self._mock_cameras}

    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        return {"success": True, "message": f"mock: {camera_id} scene={scene}",
                "data": {"grasp_pose": {"x": 350.0, "y": -120.0, "z": 200.0, "roll": 180.0, "pitch": 0.0, "yaw": 90.0}, "confidence": 0.95}}

    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        return {"success": True, "message": f"mock: streaming {camera_id} {stream_type}"}

    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        return {"success": True, "message": f"mock: stopped {camera_id}"}


class RealCameraClient(CameraClientBase):
    """通过 ROS2 Service 与 camera_manager_node 通信。

    复用已有的 service_client (Ros2ServiceClientBase)，不再每次 new。
    视频帧 → WS relay (app/ws/camera.py) 转发自 camera_manager_node WS。
    """

    def __init__(self, service_client=None, runtime=None, timeout: float = 10.0):
        self._service = service_client  # 复用共享的 service_client
        self._runtime = runtime
        self._timeout = timeout

    async def _call(self, service: str, params: dict) -> dict[str, Any]:
        if self._service is None:
            return {"success": False, "message": "ROS2 service client not available"}
        return await self._service.call_service(service, params)

    async def get_camera_list(self) -> dict[str, Any]:
        result = await self._call("/camera/list", {})
        if result.get("success"):
            try:
                cameras = json.loads(result.get("result_json", "[]") or "[]")
            except (json.JSONDecodeError, TypeError):
                cameras = []
            return {"success": True, "cameras": cameras}
        return {"success": False, "message": result.get("message", "Failed")}

    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        return await self._call("/camera/stream/start", {"camera_id": camera_id})

    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        return await self._call("/camera/stream/stop", {"camera_id": camera_id})

    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        if self._runtime is None:
            return {"success": False, "message": "ROS2 runtime not available"}
        from control_interfaces.srv import VisionDetect
        from rclpy.node import Node
        import asyncio

        node: Node = self._runtime.node
        client = node.create_client(VisionDetect, "/vision_detect")
        if not client.wait_for_service(timeout_sec=5.0):
            return {"success": False, "message": "VisionDetect service not available"}
        req = VisionDetect.Request()
        req.camera_id = camera_id
        req.scene = scene
        result = await self._bridge_future(client.call_async(req))
        if result.get("success"):
            return {"success": True, "message": "Detection completed",
                    "data": {"grasp_pose": {
                        "x": result.get("x", 0.0), "y": result.get("y", 0.0),
                        "z": result.get("z", 0.0), "roll": result.get("roll", 0.0),
                        "pitch": result.get("pitch", 0.0), "yaw": result.get("yaw", 0.0),
                    }}}
        return result

    async def _bridge_future(self, ros_future) -> dict[str, Any]:
        import asyncio
        loop = asyncio.get_event_loop()
        aio_future = loop.create_future()

        def _done_callback(fut):
            if aio_future.done(): return
            try:
                resp = fut.result()
                loop.call_soon_threadsafe(aio_future.set_result, {
                    "success": bool(resp.success), "message": getattr(resp, "message", ""),
                    "x": getattr(resp, "x", 0.0), "y": getattr(resp, "y", 0.0),
                    "z": getattr(resp, "z", 0.0), "roll": getattr(resp, "roll", 0.0),
                    "pitch": getattr(resp, "pitch", 0.0), "yaw": getattr(resp, "yaw", 0.0),
                })
            except Exception as e:
                loop.call_soon_threadsafe(aio_future.set_exception, e)

        ros_future.add_done_callback(_done_callback)
        try:
            return await asyncio.wait_for(aio_future, timeout=self._timeout)
        except asyncio.TimeoutError:
            return {"success": False, "message": f"Service timed out after {self._timeout}s"}

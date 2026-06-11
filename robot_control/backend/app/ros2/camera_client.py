import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

try:
    from rclpy.node import Node

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class CameraClientBase(ABC):
    @abstractmethod
    async def get_camera_list(self) -> dict[str, Any]:
        """返回所有已配置相机的信息列表。"""
        ...

    @abstractmethod
    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        """执行视觉检测，返回抓取位姿。"""
        ...

    @abstractmethod
    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        """启动指定相机的帧采集。"""
        ...

    @abstractmethod
    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        """停止指定相机的帧采集。"""
        ...


class MockCameraClient(CameraClientBase):
    def __init__(self):
        self._mock_cameras = [
            {
                "id": "head", "name": "头部相机 (Mock)", "position": "head",
                "connected": True, "serial": "MOCK001",
                "color_width": 1280, "color_height": 720, "color_fps": 30,
                "depth_width": 848, "depth_height": 480, "depth_fps": 30,
            },
            {
                "id": "left_arm", "name": "左臂相机 (Mock)", "position": "left_arm",
                "connected": True, "serial": "MOCK002",
                "color_width": 640, "color_height": 480, "color_fps": 30,
                "depth_width": 640, "depth_height": 400, "depth_fps": 30,
            },
            {
                "id": "right_arm", "name": "右臂相机 (Mock)", "position": "right_arm",
                "connected": False, "serial": "",
                "color_width": 0, "color_height": 0, "color_fps": 0,
                "depth_width": 0, "depth_height": 0, "depth_fps": 0,
            },
        ]

    async def get_camera_list(self) -> dict[str, Any]:
        return {"success": True, "cameras": self._mock_cameras}

    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        return {
            "success": True,
            "message": f"mock: detection on {camera_id} scene={scene}",
            "data": {
                "grasp_pose": {
                    "x": 350.0, "y": -120.0, "z": 200.0,
                    "roll": 180.0, "pitch": 0.0, "yaw": 90.0,
                },
                "confidence": 0.95,
            },
        }

    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        return {"success": True, "message": f"mock: streaming {camera_id} {stream_type}"}

    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        return {"success": True, "message": f"mock: stopped {camera_id}"}


class RealCameraClient(CameraClientBase):
    """通过 camera_manager 管理相机 (pyorbbecsdk 直连)。

    不再直接订阅 ROS2 topic。帧获取由 camera_ws_handler 通过
    camera_manager 的同步 getter 完成。
    detect_grasp_pose 仍需要 ROS2 runtime 来调用 VisionDetect service。
    """

    def __init__(self, runtime=None, timeout: float = 10.0):
        self._runtime = runtime  # 仅用于 detect_grasp_pose
        self._timeout = timeout

    async def get_camera_list(self) -> dict[str, Any]:
        from python_pkgs.vision.camera_manager import get_camera_manager

        mgr = get_camera_manager()
        if mgr is None:
            return {"success": False, "message": "CameraManager not initialized"}
        return {"success": True, "cameras": mgr.get_camera_list()}

    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        """调用 ROS2 VisionDetect service (保留原有逻辑)。"""
        if self._runtime is None:
            return {"success": False, "message": "ROS2 runtime not available for VisionDetect"}

        from control_interfaces.srv import VisionDetect

        node: Node = self._runtime.node
        client = node.create_client(VisionDetect, "/vision_detect")
        if not client.wait_for_service(timeout_sec=5.0):
            return {"success": False, "message": "VisionDetect service not available"}

        req = VisionDetect.Request()
        req.camera_id = camera_id
        req.scene = scene
        result = await self._bridge_future(client.call_async(req))
        if result.get("success"):
            return {
                "success": True,
                "message": "Detection completed",
                "data": {
                    "grasp_pose": {
                        "x": result.get("x", 0.0),
                        "y": result.get("y", 0.0),
                        "z": result.get("z", 0.0),
                        "roll": result.get("roll", 0.0),
                        "pitch": result.get("pitch", 0.0),
                        "yaw": result.get("yaw", 0.0),
                    },
                },
            }
        return result

    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        from python_pkgs.vision.camera_manager import get_camera_manager

        mgr = get_camera_manager()
        if mgr is None:
            return {"success": False, "message": "CameraManager not initialized"}
        return mgr.start_stream(camera_id)

    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        from python_pkgs.vision.camera_manager import get_camera_manager

        mgr = get_camera_manager()
        if mgr is None:
            return {"success": False, "message": "CameraManager not initialized"}
        return mgr.stop_stream(camera_id)

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
                    "x": getattr(response, "x", 0.0),
                    "y": getattr(response, "y", 0.0),
                    "z": getattr(response, "z", 0.0),
                    "roll": getattr(response, "roll", 0.0),
                    "pitch": getattr(response, "pitch", 0.0),
                    "yaw": getattr(response, "yaw", 0.0),
                }
                loop.call_soon_threadsafe(aio_future.set_result, result)
            except Exception as exc:
                loop.call_soon_threadsafe(aio_future.set_exception, exc)

        ros_future.add_done_callback(_done_callback)

        try:
            return await asyncio.wait_for(aio_future, timeout=self._timeout)
        except asyncio.TimeoutError:
            return {"success": False, "message": f"Service timed out after {self._timeout}s"}

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

try:
    from rclpy.node import Node

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False

CAMERA_TOPICS = {
    "camera_1": {
        "raw": "/camera_1/color/image_raw",
        "depth": "/camera_1/depth/image_raw",
    },
    "camera_2": {
        "raw": "/camera_2/color/image_raw",
        "depth": "/camera_2/depth/image_raw",
    },
    "camera_3": {
        "raw": "/camera_3/color/image_raw",
        "depth": "/camera_3/depth/image_raw",
    },
}


class CameraClientBase(ABC):
    @abstractmethod
    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        """Run vision detection on the specified camera, return grasp pose."""
        ...

    @abstractmethod
    async def start_stream(self, camera_id: str, stream_type: str) -> dict[str, Any]:
        """Start capturing frames for the given camera and stream type."""
        ...

    @abstractmethod
    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        """Stop capturing frames."""
        ...

    @abstractmethod
    async def get_frame(self, camera_id: str) -> bytes | None:
        """Get the latest JPEG frame. Returns None if no frame available."""
        ...


class MockCameraClient(CameraClientBase):
    def __init__(self):
        self._active_camera: str | None = None

    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        return {
            "success": True,
            "message": f"mock: detection on {camera_id} scene={scene}",
            "data": {
                "grasp_pose": {
                    "x": 350.0,
                    "y": -120.0,
                    "z": 200.0,
                    "roll": 180.0,
                    "pitch": 0.0,
                    "yaw": 90.0,
                },
                "confidence": 0.95,
            },
        }

    async def start_stream(self, camera_id: str, stream_type: str) -> dict[str, Any]:
        self._active_camera = camera_id
        return {"success": True, "message": f"mock: streaming {camera_id} {stream_type}"}

    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        self._active_camera = None
        return {"success": True, "message": f"mock: stopped {camera_id}"}

    async def get_frame(self, camera_id: str) -> bytes | None:
        return None


class RealCameraClient(CameraClientBase):
    """Subscribes to Orbbec camera ROS2 topics and converts to JPEG frames.

    Three cameras expected on topics:
      /camera_1/color/image_raw (sensor_msgs/Image)
      /camera_2/color/image_raw
      /camera_3/color/image_raw

    Frames are converted to JPEG via cv_bridge for web streaming.
    """

    def __init__(self, runtime, timeout: float = 10.0):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed")
        self._runtime = runtime
        self._timeout = timeout
        self._subs: dict[str, Any] = {}
        self._latest_frame: dict[str, bytes] = {}
        self._active_camera: str | None = None

    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
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

    async def start_stream(self, camera_id: str, stream_type: str) -> dict[str, Any]:
        if camera_id not in CAMERA_TOPICS:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}

        # Stop any existing stream
        if self._active_camera and self._active_camera != camera_id:
            await self.stop_stream(self._active_camera)

        if camera_id in self._subs:
            return {"success": True, "message": f"Already streaming {camera_id}"}

        from sensor_msgs.msg import Image

        topic = CAMERA_TOPICS[camera_id].get(stream_type, CAMERA_TOPICS[camera_id]["raw"])

        def _cb(msg: Image):
            try:
                import cv2
                import numpy as np
                from cv_bridge import CvBridge

                bridge = getattr(self, "_bridge", None)
                if bridge is None:
                    bridge = CvBridge()
                    self._bridge = bridge

                if stream_type == "depth":
                    cv_image = bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
                    cv_image = cv2.normalize(cv_image, None, 0, 255, cv2.NORM_MINMAX)
                    cv_image = np.uint8(cv_image)
                    _, jpeg = cv2.imencode(".jpg", cv_image)
                else:
                    cv_image = bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
                    if stream_type == "grayscale":
                        cv_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
                    _, jpeg = cv2.imencode(".jpg", cv_image)

                self._latest_frame[camera_id] = jpeg.tobytes()
            except Exception:
                logger.exception("Failed to convert camera frame")

        node: Node = self._runtime.node
        sub = node.create_subscription(Image, topic, _cb, 10)
        self._subs[camera_id] = sub
        self._active_camera = camera_id
        logger.info("Camera stream started: %s (%s) on %s", camera_id, stream_type, topic)
        return {"success": True, "message": f"Streaming {camera_id} {stream_type}"}

    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        sub = self._subs.pop(camera_id, None)
        if sub is not None:
            self._runtime.node.destroy_subscription(sub)
            self._latest_frame.pop(camera_id, None)
            logger.info("Camera stream stopped: %s", camera_id)
        if self._active_camera == camera_id:
            self._active_camera = None
        return {"success": True, "message": f"Stopped {camera_id}"}

    async def get_frame(self, camera_id: str) -> bytes | None:
        return self._latest_frame.get(camera_id)

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

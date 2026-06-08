import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from control_interfaces.srv import VisionDetect
import logging

logger = logging.getLogger(__name__)

CAMERA_TOPICS = {
    "camera_1": {
        "color": "/camera_1/color/image_raw",
        "depth": "/camera_1/depth/image_raw",
    },
    "camera_2": {
        "color": "/camera_2/color/image_raw",
        "depth": "/camera_2/depth/image_raw",
    },
    "camera_3": {
        "color": "/camera_3/color/image_raw",
        "depth": "/camera_3/depth/image_raw",
    },
}


class VisionDetectNode(Node):
    def __init__(self):
        super().__init__("vision_detect_node")

        self._color_subs: dict[str, object] = {}
        self._depth_subs: dict[str, object] = {}
        self._latest_color: dict[str, Image | None] = {}
        self._latest_depth: dict[str, Image | None] = {}

        self.srv = self.create_service(VisionDetect, "/vision_detect", self.handle_detect)
        self.get_logger().info("VisionDetect service ready on /vision_detect")

    def _ensure_subs(self, camera_id: str):
        if camera_id not in CAMERA_TOPICS:
            return
        if camera_id in self._color_subs:
            return
        topics = CAMERA_TOPICS[camera_id]
        self._latest_color[camera_id] = None
        self._latest_depth[camera_id] = None

        self._color_subs[camera_id] = self.create_subscription(
            Image, topics["color"],
            lambda msg, cid=camera_id: self._color_cb(cid, msg),
            10,
        )
        self._depth_subs[camera_id] = self.create_subscription(
            Image, topics["depth"],
            lambda msg, cid=camera_id: self._depth_cb(cid, msg),
            10,
        )
        self.get_logger().info(f"Subscribed to {camera_id}: {topics['color']}, {topics['depth']}")

    def _color_cb(self, camera_id: str, msg: Image):
        self._latest_color[camera_id] = msg

    def _depth_cb(self, camera_id: str, msg: Image):
        self._latest_depth[camera_id] = msg

    def handle_detect(self, request, response):
        camera_id = request.camera_id
        scene = request.scene

        if camera_id not in CAMERA_TOPICS:
            response.success = False
            response.message = f"Unknown camera: {camera_id}"
            return response

        self._ensure_subs(camera_id)

        color = self._latest_color.get(camera_id)
        depth = self._latest_depth.get(camera_id)

        if color is None:
            response.success = False
            response.message = f"No frame available for {camera_id}"
            return response

        # TODO: Implement real detection logic here
        # 1. Convert color Image to cv2 via cv_bridge
        # 2. Run YOLO/segmentation model for scene-specific object detection
        # 3. If depth is available, compute median depth around detection center
        # 4. Convert 2D pixel + depth → 3D camera coordinates using camera intrinsics
        # 5. Transform camera coordinates → robot base/grasp frame using TF
        #
        # For now, return a placeholder grasp pose.
        response.success = True
        response.message = f"Placeholder detection: camera={camera_id}, scene={scene}"
        response.x = 350.0
        response.y = -120.0
        response.z = 200.0
        response.roll = 180.0
        response.pitch = 0.0
        response.yaw = 90.0

        self.get_logger().info(
            f"Detection request: camera={camera_id}, scene={scene} → "
            f"placeholder pose ({response.x}, {response.y}, {response.z})"
        )
        return response


def main(args=None):
    rclpy.init(args=args)
    node = VisionDetectNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

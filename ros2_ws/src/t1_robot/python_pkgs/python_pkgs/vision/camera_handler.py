import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Image
from cv_bridge import CvBridge
import time
import numpy as np

class CameraHandler:
    """管理单个相机：保存最近一帧 RGB+Depth，支持懒订阅"""
    def __init__(self, node: Node, name: str, rgb_topic: str, depth_topic: str,
                 detector, pub_topic: str, conf=0.5, mode="detect"):
        self.node = node
        self.name = name
        self.detector = detector
        self.bridge = CvBridge()
        self.mode = mode
        self.conf = conf
        self.rgb_frame = None
        self.depth_frame = None
        self.last_rgb_time = 0.0
        self.last_depth_time = 0.0

        # 订阅RGB与Depth
        self.rgb_sub = node.create_subscription(CompressedImage, rgb_topic, self.rgb_callback, 10)
        self.depth_sub = node.create_subscription(Image, depth_topic, self.depth_callback, 10)

        # 懒订阅发布
        self.img_pub = node.create_publisher(Image, f'/yolo_detections/{name}', 10)
        #以json格式发布检测结果
        self.result_pub = node.create_publisher(String, f'/yolo_detections/{name}/result', 10)

        # 后台检测线程
        import threading
        self.running = True
        self.thread = threading.Thread(target=self.detect_loop, daemon=True)
        self.thread.start()

    def rgb_callback(self, msg):
        self.rgb_frame = self.bridge.compressed_imgmsg_to_cv2(msg)
        self.last_rgb_time = time.time()

    def depth_callback(self, msg):
        self.depth_frame = self.bridge.imgmsg_to_cv2(msg, "passthrough")
        self.last_depth_time = time.time()

    def get_latest_frames(self):
        """返回最近一帧 (rgb, depth)"""
        return self.rgb_frame, self.depth_frame

    def detect_loop(self):
        """懒订阅实时检测"""
        while rclpy.ok() and self.running:
            if self.img_pub.get_subscription_count() > 0 and self.rgb_frame is not None:
                result = self.detector.infer(self.rgb_frame, mode=self.mode)
                annotated = result.plot()
                img_msg = self.bridge.cv2_to_imgmsg(annotated, "bgr8")
                self.img_pub.publish(img_msg)
                self.node.get_logger().info(f"[{self.name}] YOLO {self.mode} detection published.")
                detections = []
                for b in result.boxes:
                    x1, y1, x2, y2 = b.xyxy[0].cpu().numpy()
                    detections.append({
                        "class": int(b.cls[0]),
                        "conf": float(b.conf[0]),
                        "box": [x1, y1, x2, y2]
                    })
                msg = String()
                msg.data = json.dumps({
                    "camera": self.name,
                    "n": len(detections),
                    "detections": detections
                })
                self.result_pub.publish(msg)

            time.sleep(0.1)

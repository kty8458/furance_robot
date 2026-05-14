import sys
import os
from ultralytics import YOLO
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import Point
from cv_bridge import CvBridge
# from python_pkgs.vision.camera_handler import CameraHandler
from camera_handler import CameraHandler
from control_interfaces.srv import YoloInference
import numpy as np
import cv2

class YoloDetector:
    """封装检测与分割模型"""
    def __init__(self, detect_model_path, seg_model_path=None, conf=0.5):
        self.detect_model = YOLO(detect_model_path)
        self.seg_model = YOLO(seg_model_path) if seg_model_path else None
        self.conf = conf

    def infer(self, img, mode="detect"):
        model = self.seg_model if (mode == "segment" and self.seg_model) else self.detect_model
        results = model.predict(img, conf=self.conf, verbose=False)
        return results[0]

class YoloRos2Node(Node):
    def __init__(self):
        super().__init__('yolo_ros2_node')

        # ---------------- 参数 ----------------
        self.declare_parameter('detect_model_path', '/home/test/wheel_arm_ws/src/python_pkgs/python_pkgs/vision/best2.onnx')
        # self.declare_parameter('seg_model_path', '/home/test/wheel_arm_ws/src/python_pkgs/python_pkgs/vision/yolo_seg.onnx')
        self.declare_parameter('conf_threshold', 0.5)
        self.declare_parameter('mode', 'detect')
        self.declare_parameter('fx', 614.0)
        self.declare_parameter('fy', 614.0)
        self.declare_parameter('cx', 320.0)
        self.declare_parameter('cy', 240.0)

        detect_model = self.get_parameter('detect_model_path').value
        # seg_model = self.get_parameter('seg_model_path').value
        conf = self.get_parameter('conf_threshold').value
        self.mode = self.get_parameter('mode').value

        # 相机内参
        self.fx = self.get_parameter('fx').value
        self.fy = self.get_parameter('fy').value
        self.cx = self.get_parameter('cx').value
        self.cy = self.get_parameter('cy').value
        
        #TODO 加载三个相机外参

        # YOLO 模型
        self.detector = YoloDetector(detect_model, None, conf)
        self.bridge = CvBridge()
        self.get_logger().info(f"YOLO node started in {self.mode} mode")

        # ---------------- 三相机 ----------------
        self.cameras = [
            CameraHandler(self, 'head',
                '/camera/camera/color/image_raw/compressed',
                '/camera/camera/aligned_depth_to_color/image_raw',
                self.detector, '/yolo_detections/head', conf, self.mode),
            # CameraHandler(self, 'head',
            #               '/head_camera/color/image_raw/compressed',
            #               '/head_camera/aligned_depth_to_color/image_raw',
            #               self.detector, '/yolo_detections/head', conf, self.mode),
            # CameraHandler(self, 'left',
            #               '/left_camera/color/image_raw/compressed',
            #               '/left_camera/aligned_depth_to_color/image_raw',
            #               self.detector, '/yolo_detections/left', conf, self.mode),
            # CameraHandler(self, 'right',
            #               '/right_camera/color/image_raw/compressed',
            #               '/right_camera/aligned_depth_to_color/image_raw',
            #               self.detector, '/yolo_detections/right', conf, self.mode),
        ]

        # ---------------- 服务接口 ----------------
        self.srv = self.create_service(YoloInference, 'yolo_inference', self.handle_inference)

    # ---------------- 核心：服务调用推理 ----------------
    def handle_inference(self, request, response):
        camera_id = int(request.camera_id)
        mode = request.mode
        target_class = int(request.target_class)

        if camera_id < 0 or camera_id >= len(self.cameras):
            self.get_logger().error(f"Invalid camera_id={camera_id}")
            response.success = False
            return response

        cam = self.cameras[camera_id]
        rgb, depth = cam.get_latest_frames()

        if rgb is None:
            self.get_logger().warn(f"[{cam.name}] No RGB frame available.")
            response.success = False
            return response

        if depth is None:
            depth = np.zeros((rgb.shape[0], rgb.shape[1]), dtype=np.uint16)

        # ---------------- YOLO 推理 ----------------
        result = self.detector.infer(rgb, mode=mode)
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            response.success = False
            self.get_logger().info("No boxes detected.")
            return response

        # 筛选目标类别
        candidates = [(float(b.conf[0]), b) for b in boxes if int(b.cls[0]) == target_class]
        if len(candidates) == 0:
            self.get_logger().info(f"No object of class {target_class}")
            response.success = False
            return response

        best_conf, best_box = max(candidates, key=lambda x: x[0])
        x1, y1, x2, y2 = best_box.xyxy[0].cpu().numpy()
        cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)

        # ---------------- 深度计算 ----------------
        h, w = depth.shape[:2]
        roi = depth[max(0, cy-3):min(h, cy+3), max(0, cx-3):min(w, cx+3)]
        roi = roi.astype(np.float32)
        roi = roi[np.isfinite(roi) & (roi > 0)]
        depth_m = np.median(roi)/1000.0 if roi.size > 0 else 0.0

        # ---------------- 坐标换算 ----------------
        Xc = (cx - self.cx) * depth_m / self.fx
        Yc = (cy - self.cy) * depth_m / self.fy
        Zc = depth_m
        #TODO 根据相机外参转换

        annotated = result.plot()
        response.annotated_image = self.bridge.cv2_to_imgmsg(annotated, "bgr8")

        if mode == "segment" and hasattr(result, "masks"):
            mask = (result.masks.data[0].cpu().numpy() * 255).astype(np.uint8)
            response.mask_image = self.bridge.cv2_to_imgmsg(mask, "mono8")

        response.object_position = Point(x=float(Xc), y=float(Yc), z=float(Zc))
        response.success = True

        self.get_logger().info(
            f"[{cam.name}] class={target_class}, conf={best_conf:.2f}, "
            f"depth={depth_m:.3f}m, XYZ=({Xc:.3f},{Yc:.3f},{Zc:.3f})"
        )
        return response

class YoloClient(Node):
    def __init__(self):
        super().__init__('yolo_client')
        self.bridge = CvBridge()
        self.result_cache = None
        self.image_cache = None
        self.sub_result = None
        self.sub_image = None
        self.running = False

        # 服务客户端
        self.cli = self.create_client(YoloInference, '/yolo_inference')
        if not self.cli.wait_for_service(timeout_sec=5.0):
            self.get_logger().error("Service /yolo_inference not available.")
        else:
            self.get_logger().info("Service connected.")

    def call_once(self, camera_id=0, target_class=0, mode='detect'):
        """单帧服务调用"""
        req = YoloInference.Request()
        req.camera_id = camera_id
        req.target_class = target_class
        req.mode = mode
        self.get_logger().info(f"Calling inference: camera_id={camera_id}, class={target_class}, mode={mode}")
        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=8.0)
        resp = future.result()
        if not resp or not resp.success:
            self.get_logger().warn("Inference failed.")
            return None
        self.image_cache = self.bridge.imgmsg_to_cv2(resp.annotated_image, "bgr8")
        self.get_logger().info(f"Inference OK, 3D pos=({resp.object_position.x:.3f}, {resp.object_position.y:.3f}, {resp.object_position.z:.3f})")
        return resp

    def start_subscribe(self, camera_name='head'):
        """开始订阅实时检测结果话题"""
        if self.running:
            self.get_logger().info("Already subscribed.")
            return
        self.running = True
        result_topic = f"/yolo_detections/{camera_name}/result"
        image_topic = f"/yolo_detections/{camera_name}"
        self.sub_result = self.create_subscription(DetectionResult, result_topic, self.result_cb, 10)
        self.sub_image = self.create_subscription(Image, image_topic, self.image_cb, 10)
        self.get_logger().info(f"Subscribed to {result_topic} and {image_topic}")

    def stop_subscribe(self):
        """停止订阅"""
        if not self.running:
            return
        self.destroy_subscription(self.sub_result)
        self.destroy_subscription(self.sub_image)
        self.sub_result = None
        self.sub_image = None
        self.running = False
        self.get_logger().info("Unsubscribed from YOLO topics.")

    def result_cb(self, msg):
        """检测结果回调"""
        self.result_cache = msg
        self.get_logger().info(f"Received {len(msg.class_ids)} detections from cam{msg.camera_id}")

    def image_cb(self, msg):
        """检测图像回调"""
        self.image_cache = self.bridge.imgmsg_to_cv2(msg, "bgr8")

    def get_latest_result(self):
        return self.result_cache, self.image_cache


def main(args=None):
    rclpy.init(args=args)
    node = YoloRos2Node()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
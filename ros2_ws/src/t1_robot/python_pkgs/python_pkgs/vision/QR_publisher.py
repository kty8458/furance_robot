import os
import sys
#配置环境为yolo虚拟环境
venv_path = "/workspaces/isaac_ros-dev/src/python_pkgs/venvs/yolo"
python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"
site_packages = os.path.join(venv_path, "lib", python_version, "site-packages")
bin_path = os.path.join(venv_path, "bin")
# 注入环境变量
os.environ["PATH"] = f"{bin_path}{os.pathsep}{os.environ['PATH']}"
os.environ["VIRTUAL_ENV"] = venv_path
# 添加包路径
sys.path.insert(0, site_packages)

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32MultiArray
import cv2
import cv2.aruco as aruco
import numpy as np
from cv_bridge import CvBridge
from scipy.spatial.transform import Rotation as R
import math
from control_interfaces.srv import QRDetection
from geometry_msgs.msg import Point, Pose
from std_msgs.msg import String
import json

class QR_Subscriber_Node(Node):
    def __init__(self):
        super().__init__('qr_sublisher_node')
        self.qrs= {}
        self.subscription = self.create_subscription(
            Image,
            '/qr_pose',  # 输入话题
            self.qr_callback,
            15
        )
    
    def qr_callback(self, msg):
        self.qrs = {}
        data_dict = json.loads(msg.data)
        if len(data_dict["ids"]) > 0:
            for i in range(len(data_dict["ids"])):
                qr = [data_dict["points"][i], data_dict["angles"][0]]
                self.qrs[data_dict["ids"]] = qr



class QR_Publisher_Node(Node):
    def __init__(self):
        super().__init__('qr_publisher_node')

        self.bridge = CvBridge()

        # ArUco 参数
        self.marker_lengths = [0.15,0.058, 0.058]  # 二维码边长（米）
        self.aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_100)
        self.ArucoDetector = aruco.ArucoDetector(self.aruco_dict)


        # 设置相机内参（根据你的相机参数替换）
        self.camera_matrix = np.array([
            [614.0, 0.0, 320.0],  # fx, 0, cx
            [0.0, 614.0, 240.0],  # 0, fy, cy
            [0.0, 0.0, 1.0]
        ])
        self.dist_coeffs = np.zeros(5)  # 假设无畸变

        self.subscription = self.create_subscription(
            Image,
            '/camera/color/image_raw',  # 输入话题
            self.image_callback,
            15
        )

        self.img_publisher = self.create_publisher(
            Image, 
            '/image_qr',  # 输出话题
            15
        )
        
        self.qr_pose_publisher = self.create_publisher(
            String,
            'qr_pose',
            15
        )

    def my_estimatePoseSingleMarker(self, corner, marker_size, mtx, distortion):
        '''
        This will estimate the rvec and tvec for each of the marker corners detected by:
        corners, ids, rejectedImgPoints = detector.detectMarkers(image)
        corners - is an array of detected corners for each detected marker in the image
        marker_size - is the size of the detected markers
        mtx - is the camera matrix
        distortion - is the camera distortion matrix
        RETURN list of rvecs, tvecs, and trash (so that it corresponds to the old estimatePoseSingleMarkers())
        '''
        marker_points = np.array([[-marker_size / 2, marker_size / 2, 0],
                                [marker_size / 2, marker_size / 2, 0],
                                [marker_size / 2, -marker_size / 2, 0],
                                [-marker_size / 2, -marker_size / 2, 0]], dtype=np.float32)
        nada, R, t = cv2.solvePnP(marker_points, corner, mtx, distortion, False, cv2.SOLVEPNP_IPPE_SQUARE)
        rvec = R
        tvec = t
        trash= nada
        return rvec, tvec, trash



    def calculate_projection_and_angle(self, rotation_matrix_torso):
        # Step 1: 获取标记的 z 轴向量
        z_vector = rotation_matrix_torso[:, 2]  # 旋转矩阵的第三列是标记的 z 轴

        # Step 2: 将 z 轴投影到 torso 坐标系的 xy 平面上 (将 z 分量置为 0)
        projection_vector = np.array([z_vector[0], z_vector[1], 0])

        # Step 3: 归一化投影向量
        norm_projection = np.linalg.norm(projection_vector)
        if norm_projection != 0:
            projection_vector /= norm_projection  # 使投影向量5单位化

        # Step 4: 计算投影向量和 torso 坐标系 y 轴之间的夹角
        e_y = np.array([0, 1, 0])  # torso 坐标系的 y 轴单位向量

        # 使用 atan2 计算投影向量和 y 轴的角度（弧度）
        angle_rad = np.arctan2(projection_vector[0], projection_vector[1])  # 与 y 轴的夹角

        # 将弧度转换为角度（-180到180度）
        angle_deg = np.degrees(angle_rad)

        # 如果 angle_deg 为负数，调整到 [0, 180] 范围
        if angle_deg < 0:
            angle_deg = 180 + angle_deg

        return projection_vector, angle_deg


    def image_callback(self, msg):
        try:
            # 使用 CvBridge 将 ROS Image 转为 OpenCV 图像
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().error(f"Failed to convert image: {e}")
            return
        
        combine_data = {
            "ids": [],
            "points": [],
            "angles": []
        }

        # 从 tf2 获取到的从 camera_color_optical_frame 到 torso 的变换矩阵
        t_translation = np.array([[0.111], [0.032], [0.722]])  # 平移向量
        R_camera_to_torso = np.array([
            [-0.005, -0.774, 0.634],
            [-1.000, 0.005, -0.002],
            [-0.002, -0.634, -0.774]
        ])  # 旋转矩阵

        # 转灰度图
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

        # 检测 ArUco 标记
        corners, ids, _ = self.ArucoDetector.detectMarkers(gray)
        aruco.drawDetectedMarkers(cv_image, corners)
        if ids is not None:
            for i, id in enumerate(ids):
                if int(id) >= len(self.marker_lengths):
                    continue
                marker_length = self.marker_lengths[int(id)]
                corner = corners[i]
                rvec, tvec, _ = self.my_estimatePoseSingleMarker(corner, marker_length, self.camera_matrix, self.dist_coeffs)
                cv2.drawFrameAxes(cv_image, self.camera_matrix, self.dist_coeffs, rvec, tvec, 0.1)
                # 将旋转向量转换为旋转矩阵
                rotation_matrix, _ = cv2.Rodrigues(rvec)

                # 1. 将二维码在相机坐标系中的位置（tvec_camera）与相机到 torso 的变换结合
                tvec_torso = np.dot(R_camera_to_torso, tvec.reshape(3,1)) + t_translation  # 先旋转，再平移

                # 2. 将二维码的旋转矩阵与相机到 torso 的旋转矩阵结合
                rotation_matrix_torso = np.dot(R_camera_to_torso, rotation_matrix)

                # 计算二维码在 torso 坐标系的角度
                _, angle_deg = self.calculate_projection_and_angle(rotation_matrix_torso)
                combine_data["ids"].append(int(id))
                combine_data["points"].append([float(tvec_torso[0][0]-0.045), float(tvec_torso[1][0]), float(tvec_torso[2][0])])
                combine_data["angles"].append(float(angle_deg))
            qrmsg = String()
            qrmsg.data = json.dumps(combine_data)
            self.qr_pose_publisher.publish(qrmsg)
        ros_img = self.bridge.cv2_to_imgmsg(cv_image, encoding='bgr8')
        self.img_publisher.publish(ros_img)


def main(args=None):
    rclpy.init(args=args)
    node = QR_Publisher_Node()
    rclpy.spin(node)

    rclpy.shutdown()

if __name__ == '__main__':
    main()
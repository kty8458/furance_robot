import sys
sys.path.append("..") 
from vision.yolo_dect import YOLOROS2Node, YoloClient
from action_client_test.action_test import MovePClient
import cv2
import rclpy
from geometry_msgs.msg import Pose, PointStamped, Point
import time
import subprocess
from control_interfaces.srv import ManageObstacle
import math
import numpy as np

def transform_coordinates(pose_0, camera_xyz, angle):
    """将局部坐标转换为全局坐标
    参数:
        p_Q0 (np.array): 物体在局部坐标系下的坐标 [x0, y0, z0]
        R (np.array): 旋转矩阵 (3x3)
        t (np.array): 平移向量 [tx, ty, tz]
    返回:
        p_W (np.array): 全局坐标系下的坐标 [x, y, z]
    """
    t = np.array([camera_xyz.x, camera_xyz.y, camera_xyz.z])
    yaw = np.radians(angle)  # 绕Z轴旋转30度 (假设只有Z轴旋转)
    R_z = np.array([
        [np.cos(yaw), -np.sin(yaw), 0],
        [np.sin(yaw), np.cos(yaw), 0],
        [0, 0, 1]
    ])  # Z轴旋转矩阵
    return R_z @ pose_0 + t

def rot_z(angle):
    w0, x0, y0, z0 = 1.0, 0.0, 0.0, 0.0

    # 转换角度为弧度
    theta = math.radians(angle)

    # 绕Z轴旋转四元数
    cos_half = math.cos(theta / 2)
    sin_half = math.sin(theta / 2)
    q_rot = (cos_half, 0.0, 0.0, sin_half)  # (w, x, y, z)

    # 四元数乘法（q_rot ⊗ q_initial）
    w_new = q_rot[0]*w0 - q_rot[1]*x0 - q_rot[2]*y0 - q_rot[3]*z0
    x_new = q_rot[0]*x0 + q_rot[1]*w0 + q_rot[2]*z0 - q_rot[3]*y0
    y_new = q_rot[0]*y0 - q_rot[1]*z0 + q_rot[2]*w0 + q_rot[3]*x0
    z_new = q_rot[0]*z0 + q_rot[1]*y0 - q_rot[2]*x0 + q_rot[3]*w0

    return (w_new, x_new, y_new, z_new)

def main():
    rclpy.init()
    detect_client = YoloClient()
    obstacle_dict = {}
    while True:
        time.sleep(3)
        result = detect_client.get_image(1) 
        if result['success'] == False:
            print("错误：获取图像失败")
            continue
        frame = result['image']
        result = detect_client.detect_QR(image=frame, QR_id=0, QR_size=0.15)
        print(result)
        if result['success'] == False:
            # print("调用失败")
            if "1" in obstacle_dict:
                detect_client.manage_obstacle(
                    operation=ManageObstacle.Request.REMOVE,
                    obstacle_id=obstacle_dict["1"]
                )
                obstacle_dict.pop("1",None)
            continue

        try:
            camera_xyz = result['position']
            camera_xyz.x -= 0.02 
            camera_xyz.y -= 0.02
            angle = result['angle']
        except:
            continue
        # if "1" in obstacle_dict:
        #     continue
        qr_w, qr_x, qr_y, qr_z = rot_z(int(90-angle))
        box1_qr_pose = np.array([0.12, 0.21, -0.325])
        box1_robot_pose = transform_coordinates(box1_qr_pose, camera_xyz, int(90-angle))
        box1 = Pose()
        box1.position.x = box1_robot_pose[0]
        box1.position.y = box1_robot_pose[1]
        box1.position.z = box1_robot_pose[2]
        box1.orientation.w = qr_w
        box1.orientation.z = qr_z
        box1.orientation.y = qr_y
        box1.orientation.x = qr_x
        detect_client.manage_obstacle(
            operation=ManageObstacle.Request.ADD,
            shape_type=ManageObstacle.Request.BOX,
            obstacle_id="qr1_box",
            center=box1,
            dimensions=[float(0.48), float(0.04), float(1.6)]
        )
        # obstacle_dict["1"] = "qr1_box"
        box2_qr_pose = np.array([0.12, -0.27, -0.325])
        box2_robot_pose = transform_coordinates(box2_qr_pose, camera_xyz, int(90-angle))
        box2 = Pose()
        box2.position.x = box2_robot_pose[0]
        box2.position.y = box2_robot_pose[1]
        box2.position.z = box2_robot_pose[2]
        box2.orientation = box1.orientation
        detect_client.manage_obstacle(
            operation=ManageObstacle.Request.ADD,
            shape_type=ManageObstacle.Request.BOX,
            obstacle_id="qr1_box2",
            center=box2,
            dimensions=[float(0.48), float(0.04), float(1.6)]
        )
        box3_qr_pose = np.array([0.12, -0.03, -0.105])
        box3_robot_pose = transform_coordinates(box3_qr_pose, camera_xyz, int(90-angle))
        box3 = Pose()
        box3.position.x = box3_robot_pose[0]
        box3.position.y = box3_robot_pose[1]
        box3.position.z = box3_robot_pose[2]
        box3.orientation = box1.orientation
        detect_client.manage_obstacle(
            operation=ManageObstacle.Request.ADD,
            shape_type=ManageObstacle.Request.BOX,
            obstacle_id="qr1_box3",
            center=box3,
            dimensions=[float(0.2), float(0.48), float(0.04)]
        )
        box4_qr_pose = np.array([-0.01, 0.25, 0.17])
        box4_robot_pose = transform_coordinates(box4_qr_pose, camera_xyz, int(90-angle))
        box4 = Pose()
        box4.position.x = box4_robot_pose[0]
        box4.position.y = box4_robot_pose[1]
        box4.position.z = box4_robot_pose[2]
        box4.orientation = box1.orientation
        detect_client.manage_obstacle(
            operation=ManageObstacle.Request.ADD,
            shape_type=ManageObstacle.Request.BOX,
            obstacle_id="qr1_box4",
            center=box4,
            dimensions=[float(0.1), float(0.06), float(0.265)]
        )
        box5_qr_pose = np.array([-0.01, 0.41, 0.035])
        box5_robot_pose = transform_coordinates(box5_qr_pose, camera_xyz, int(90-angle))
        box5 = Pose()
        box5.position.x = box5_robot_pose[0]
        box5.position.y = box5_robot_pose[1]
        box5.position.z = box5_robot_pose[2]
        box5.orientation = box1.orientation
        detect_client.manage_obstacle(
            operation=ManageObstacle.Request.ADD,
            shape_type=ManageObstacle.Request.BOX,
            obstacle_id="qr1_box5",
            center=box5,
            dimensions=[float(0.115), float(0.23), float(0.015)]
        )
        cyc_qr_pose = np.array([-0.1, 0.30, -0.125])
        cyc_robot_pose = transform_coordinates(cyc_qr_pose, camera_xyz, int(90-angle))
        cyc = Pose()
        cyc.position.x = cyc_robot_pose[0]
        cyc.position.y = cyc_robot_pose[1]
        cyc.position.z = cyc_robot_pose[2]
        cyc.orientation = box1.orientation
        detect_client.manage_obstacle(
            operation=ManageObstacle.Request.ADD,
            shape_type=ManageObstacle.Request.CYLINDER,
            obstacle_id="qr1_cyc",
            center=cyc,
            dimensions=[float(0.18), float(0.035)]
        )

    rclpy.shutdown()

if __name__ == '__main__':
    main()


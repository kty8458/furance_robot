#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from threading import Thread
import time
import numpy as np
from control_interfaces.srv import MoveP, MoveL
from interface_pkg.srv import MoveToJointPositions, WaistControl
import copy
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp


def interpolate_pose_stamped(pose1: PoseStamped, pose2: PoseStamped, steps=50, angle_threshold_deg=1.0):
    """
    对两个 PoseStamped 位姿进行插值，返回插值结果列表
    """
    poses = []

    # 位置插值
    pos1 = np.array([pose1.pose.position.x, pose1.pose.position.y, pose1.pose.position.z])
    pos2 = np.array([pose2.pose.position.x, pose2.pose.position.y, pose2.pose.position.z])

    # 四元数插值
    quat1 = [pose1.pose.orientation.x, pose1.pose.orientation.y,
             pose1.pose.orientation.z, pose1.pose.orientation.w]
    quat2 = [pose2.pose.orientation.x, pose2.pose.orientation.y,
             pose2.pose.orientation.z, pose2.pose.orientation.w]
    if np.dot(quat1, quat2) < 0:
        quat2 = [-q for q in quat2]

    rot1 = R.from_quat(quat1)
    rot2 = R.from_quat(quat2)

    # 判断旋转角度
    relative_rot = rot1.inv() * rot2
    angle_deg = relative_rot.magnitude() * 180.0 / np.pi
    do_orientation_interp = angle_deg > angle_threshold_deg

    # 插值
    for i in range(steps + 1):
        t = i / steps
        interp_pose_stamped = PoseStamped()
        interp_pose_stamped.header = copy.deepcopy(pose1.header)  # 继承 frame_id 和 stamp（也可以设置时间插值）

        interp_pose_stamped.pose.position.x = (1 - t) * pos1[0] + t * pos2[0]
        interp_pose_stamped.pose.position.y = (1 - t) * pos1[1] + t * pos2[1]
        interp_pose_stamped.pose.position.z = (1 - t) * pos1[2] + t * pos2[2]

        if do_orientation_interp:
            key_times = [0, 1]
            key_rots = R.from_quat([quat1, quat2])  # 构建 Rotation 列表
            slerp = Slerp(key_times, key_rots)
            interp_rot = slerp([t])[0]
            q = interp_rot.as_quat()
        else:
            q = quat1

        interp_pose_stamped.pose.orientation.x = q[0]
        interp_pose_stamped.pose.orientation.y = q[1]
        interp_pose_stamped.pose.orientation.z = q[2]
        interp_pose_stamped.pose.orientation.w = q[3]

        poses.append(interp_pose_stamped)

    return poses

def expand_pose_stamped_waypoints(waypoints: list, steps_per_segment=50, angle_threshold_deg=1.0) -> list:

    """
    对 PoseStamped 列表进行插值，返回更稠密的新列表
    """
    if len(waypoints) < 2:
        return waypoints

    expanded = []
    for i in range(len(waypoints) - 1):
        segment = interpolate_pose_stamped(
            waypoints[i], waypoints[i + 1],
            steps=steps_per_segment,
            angle_threshold_deg=angle_threshold_deg
        )
        if i > 0:
            segment = segment[1:]  # 避免重复点
        expanded.extend(segment)

    return expanded

class MoveJointPositionsClient(Node):
    def __init__(self):
        super().__init__("move_joint_positions_client")

        self.cli = self.create_client(MoveToJointPositions, "/move_joint_positions")

        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Waiting for /move_joint_positions service...")

    def send_request(self, left_joints, right_joints):
        req = MoveToJointPositions.Request()
        req.left_joints = left_joints
        req.right_joints = right_joints

        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            return future.result()
        else:
            raise RuntimeError("Service call failed")

class MovePClient(Node):
    def __init__(self):
        super().__init__("movep_client")
        self.cli = self.create_client(MoveP, "move_pose")

        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Waiting for move_pose service...")

    def send_request(self, lor, pose, to_frame, reference_frame, planner):
        req = MoveP.Request()
        req.lor = lor
        req.target_pose = pose
        req.to_frame = to_frame
        req.reference_frame = reference_frame
        req.planner = planner

        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            return future.result()
        else:
            raise RuntimeError("Service call failed")
        
class MoveLClient(Node):
    def __init__(self):
        super().__init__("movel_client")
        self.cli = self.create_client(MoveL, "move_line")

        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Waiting for move_line service...")

    def send_request(self, lor, waypoints):
        req = MoveL.Request()
        req.lor = lor
        req.waypoints = waypoints

        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            return future.result()
        else:
            raise RuntimeError("Service call failed")

class MoveWaistClient(Node):
    def __init__(self):
        super().__init__("move_waist_client")
        self.cli = self.create_client(WaistControl, "/waist_control")

        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Waiting for waist_control service...")

    def send_request(self, waist_angle, waist_speed):
        req = WaistControl.Request()
        req.waist_angle = waist_angle
        req.waist_speed = waist_speed

        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            return future.result()
        else:
            raise RuntimeError("Service call failed")
        
def quat_normalize(q):
    q = np.array(q, dtype=float)
    return q / np.linalg.norm(q)

def quat_to_rot(q):
    """q = [x, y, z, w]"""
    x, y, z, w = q
    R = np.array([
        [1 - 2*(y*y + z*z),     2*(x*y - z*w),         2*(x*z + y*w)],
        [2*(x*y + z*w),         1 - 2*(x*x + z*z),     2*(y*z - x*w)],
        [2*(x*z - y*w),         2*(y*z + x*w),         1 - 2*(x*x + y*y)]
    ], dtype=float)
    return R

def quat_multiply(q1, q2):
    """Hamilton product of two quaternions q = [x,y,z,w]"""
    x1,y1,z1,w1 = q1
    x2,y2,z2,w2 = q2
    return np.array([
        w1*x2 + x1*w2 + y1*z2 - z1*y2,
        w1*y2 - x1*z2 + y1*w2 + z1*x2,
        w1*z2 + x1*y2 - y1*x2 + z1*w2,
        w1*w2 - x1*x2 - y1*y2 - z1*z2
    ])

def move_along_end_x(pose_msg, distance):
    """
    pose_msg: geometry_msgs/PoseStamped
    distance: float, x方向平移（米）
    return: PoseStamped
    """
    p = pose_msg.pose.position
    q = pose_msg.pose.orientation

    p_in = np.array([p.x, p.y, p.z], dtype=float)
    q_in = np.array([q.x, q.y, q.z, q.w], dtype=float)

    R = quat_to_rot(q_in)

    # 末端 x 轴方向
    x_dir = R[:,0]

    # 新位置
    p_out = p_in + x_dir * distance

    # 封装 PoseStamped
    out = PoseStamped()
    out.header = pose_msg.header
    out.pose.position.x = p_out[0]
    out.pose.position.y = p_out[1]
    out.pose.position.z = p_out[2]
    out.pose.orientation.x = q_in[0]
    out.pose.orientation.y = q_in[1]
    out.pose.orientation.z = q_in[2]
    out.pose.orientation.w = q_in[3]

    return out

def move_along_end_z(pose_msg, distance):
    """
    沿末端自身 Z 轴方向平移
    pose_msg: geometry_msgs/PoseStamped
    distance: float, z方向平移（米）
    return: PoseStamped
    """
    p = pose_msg.pose.position
    q = pose_msg.pose.orientation

    # 转 numpy
    p_in = np.array([p.x, p.y, p.z], dtype=float)
    q_in = np.array([q.x, q.y, q.z, q.w], dtype=float)

    # 旋转矩阵
    R = quat_to_rot(q_in)

    # 末端 Z 轴方向（第三列）
    z_dir = R[:, 2]

    # 新位置
    p_out = p_in + z_dir * distance

    # 构造返回 PoseStamped
    out = PoseStamped()
    out.header = pose_msg.header

    out.pose.position.x = p_out[0]
    out.pose.position.y = p_out[1]
    out.pose.position.z = p_out[2]

    # 姿态不变
    out.pose.orientation.x = q_in[0]
    out.pose.orientation.y = q_in[1]
    out.pose.orientation.z = q_in[2]
    out.pose.orientation.w = q_in[3]

    return out

class PoseTransformer(Node):
    def __init__(self):
        super().__init__("pose_transformer")

        # ==================================================
        # 1. 相机坐标系 → 基坐标系的静态变换（不弯腰时）
        # ==================================================
        self.t_base_cam = np.array([0.226, -0.015, 1.184], dtype=float)

        self.q_base_cam = quat_normalize([
            0.542955097994861,
            0.5341994603333162,
            0.4542114797295065,
            0.46208508937523307
        ])

        # ==================================================
        # 2. 物体相对于二维码的固定变换
        # ==================================================
        self.t_tag_obj = np.array([0.276, -0.585, 1.15], dtype=float)   
        self.q_tag_obj = quat_normalize([0.60309, -0.12577, 0.47012, 0.63009]) 

        self.t_waist_base = np.array([0.142, 0.086, 0.894], dtype=float)

        self.q_waist_base = quat_normalize([0.0, 0.707, 0.0, 0.707])
        # 最新的二维码 pose（相机下）
        self.latest_pose_tag = None

        # 订阅二维码姿态（相机坐标系下）
        self.create_subscription(
            PoseStamped,
            "/aruco_single/pose",
            self.pose_callback,
            10
        )
        self.get_logger().info("PoseTransformer initialized with background spinning.")


    def pose_callback(self, msg):
        self.latest_pose_tag = msg

    # ==================================================
    # 工具：把 Pose 转为 p, q
    # ==================================================
    @staticmethod
    def pose_to_numpy(pose_msg):
        p = pose_msg.pose.position
        q = pose_msg.pose.orientation
        return (
            np.array([p.x, p.y, p.z], dtype=float),
            np.array([q.x, q.y, q.z, q.w], dtype=float)
        )

    # ==================================================
    # 获取二维码在相机坐标系下的位姿 T_cam_tag
    # ==================================================
    def wait_for_tag_pose(self, timeout=5.0):
        start = time.time()
        while self.latest_pose_tag is None:
            if time.time() - start > timeout:
                raise RuntimeError("Timeout waiting for QR pose")
            time.sleep(0.05)

        return self.pose_to_numpy(self.latest_pose_tag)

    # ==================================================
    # 链式变换：物体(相对二维码) → 相机
    #           T_cam_obj = T_cam_tag * T_tag_obj
    # ==================================================
    def transform_tag_to_cam(self, p_tag_obj, q_tag_obj, p_cam_tag, q_cam_tag):
        R_cam_tag = quat_to_rot(q_cam_tag)
        p_cam_obj = R_cam_tag @ p_tag_obj + p_cam_tag
        q_cam_obj = quat_multiply(q_cam_tag, q_tag_obj)
        return p_cam_obj, q_cam_obj

    # ==================================================
    # 链式变换：物体(相机下) → 基坐标
    #           T_base_obj = T_base_cam * T_cam_obj
    # ==================================================
    def transform_cam_to_base(self, p_cam_obj, q_cam_obj):
        R_base_cam = quat_to_rot(self.q_base_cam)
        p_base_obj = R_base_cam @ p_cam_obj + self.t_base_cam
        q_base_obj = quat_multiply(self.q_base_cam, q_cam_obj)
        return p_base_obj, q_base_obj
    
    def transform_base_to_waist(self, p_base_obj, q_base_obj):
        """ 使用静态 T_waist_base (B) 计算 T_waist_obj """
        R_waist_base = quat_to_rot(self.q_waist_base)
        p_waist_obj = R_waist_base @ p_base_obj + self.t_waist_base
        q_waist_obj = quat_multiply(self.q_waist_base, q_base_obj)
        return p_waist_obj, q_waist_obj

    # ==================================================
    # 公开接口：直接得到物体在腰部坐标系下的 PoseStamped
    # ==================================================
    def get_pose_in_base(self, pose_tag: PoseStamped):
        """ T_base_obj = T_base_cam * T_cam_tag * T_tag_obj """
        p_cam_tag, q_cam_tag = self.pose_to_numpy(pose_tag)
        
        # T_cam_tag * T_tag_obj = T_cam_obj
        p_cam_obj, q_cam_obj = self.transform_tag_to_cam(
            self.t_tag_obj, self.q_tag_obj, p_cam_tag, q_cam_tag
        )

        # T_base_cam * T_cam_obj = T_base_obj
        p_base_obj, q_base_obj = self.transform_cam_to_base(
            p_cam_obj, q_cam_obj
        )

        # 封装成 PoseStamped
        # ⚠️ 注意：这里我们将 frame_id 设置为 base_link
        return self._create_pose_stamped(p_base_obj, q_base_obj, "base_link")


    # ==================================================
    # 公开接口 2：将 T_base_object 转换到 腰部坐标系下 (T_waist_object)
    # ==================================================
    def transform_base_to_waist_static(self, pose_in_base: PoseStamped):
        """ T_waist_obj = T_waist_base * T_base_obj """
        p_base_obj, q_base_obj = self.pose_to_numpy(pose_in_base)
        
        # T_waist_base * T_base_obj = T_waist_obj
        p_waist_obj, q_waist_obj = self.transform_base_to_waist(
            p_base_obj, q_base_obj
        )

        # 封装成 PoseStamped
        # ⚠️ 注意：这里我们将 frame_id 设置为 waist_Link
        return self._create_pose_stamped(p_waist_obj, q_waist_obj, "waist_Link")


    def _create_pose_stamped(self, p, q, frame_id):
        """ 辅助函数，将 p, q 封装为 PoseStamped """
        out = PoseStamped()
        out.header.frame_id = frame_id
        out.header.stamp = self.get_clock().now().to_msg()
        out.pose.position.x, out.pose.position.y, out.pose.position.z = p
        out.pose.orientation.x, out.pose.orientation.y, out.pose.orientation.z, out.pose.orientation.w = q
        return out
#================================================



def main(args=None):
    rclpy.init(args=args)
    node = PoseTransformer()
    movep_client = MovePClient()
    movel_client = MoveLClient()
    movej_client = MoveJointPositionsClient()
    waist_client = MoveWaistClient()
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    executor.add_node(movep_client)
    executor.add_node(movel_client)

    # 让系统跑几百毫秒，让订阅拿到 TF
    start = time.time()
    while node.latest_pose_tag is None:
        executor.spin_once(timeout_sec=0.1)
        if time.time() - start > 10:
            raise RuntimeError("QR code pose not received!")
    # ---------------------------
    executor.spin_once(timeout_sec=0.1)
    #移动到抓取位
    pose_in_waist = node.get_pose_in_base()
    print("Pose in waist_Link frame:")
    print(pose_in_waist)

    #移动到预备位
    # left_init_pose = [0.0, 30.0, 0.0, -90.0, 0.0, 0.0, 0.0]
    # right_init_pose = [0.0, -30.0, 0.0, 90.0, 0.0, 0.0, -60.0]
    # waist_client.send_request(90.0, 30)
    # movej_client.send_request(left_init_pose, right_init_pose)
    # print("预备位完成")
    # i = input("是否移动到预备位？")
    # if i != 'y':
    #     return

    # pose_in_waist = move_along_end_z(pose_in_waist, 0.1)
    # movep_client.send_request(
    #     lor="right",
    #     pose=pose_in_waist,
    #     to_frame="J7_right_Link",
    #     reference_frame="waist_Link",
    #     planner="ompl"
    # )
    # print("moveP")
    # i = input("是否移动到预备抓取位？")
    # if i != 'y':
    #     return
    # way_points = []
    # way_points.append(copy.deepcopy(pose_in_waist))
    # pose_in_waist = move_along_end_z(pose_in_waist, -0.1)   
    # way_points.append(copy.deepcopy(pose_in_waist))

    # expanded = expand_pose_stamped_waypoints(way_points, 100)
    # pose_list = [p.pose for p in expanded]
    # movel_client.send_request(
    #     lor="right",
    #     waypoints=pose_list
    # )
    # i = input("是否移动到抓取位？")
    # if i != 'y':
    #     return
    # #收回手臂
    # way_points = []
    # way_points.append(copy.deepcopy(pose_in_waist))
    # pose_in_waist = move_along_end_z(pose_in_waist, 0.15)   
    # way_points.append(copy.deepcopy(pose_in_waist))

    # expanded = expand_pose_stamped_waypoints(way_points, 100)
    # pose_list = [p.pose for p in expanded]
    # movel_client.send_request(
    #     lor="right",
    #     waypoints=pose_list
    # )
    # right_back_pose = [40.0, -40.0, -17.0, 36.0, -50.0, -95.0, 23.0]
    # movej_client.send_request(left_init_pose, right_back_pose)
    # i = input("是否移动回收位？")
    # if i != 'y':
    #     return
    # waist_client.send_request(0.0, 30)
    # time.sleep(3)
    # movej_client.send_request(left_init_pose, right_init_pose)
    executor.spin()

    node.destroy_node()
    movep_client.destroy_node()
    movel_client.destroy_node()
    rclpy.shutdown()



if __name__ == "__main__":
    main()

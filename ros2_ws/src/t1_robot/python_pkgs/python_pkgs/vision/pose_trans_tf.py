import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from tf2_ros import Buffer, TransformListener
import numpy as np
import threading
from geometry_msgs.msg import PoseStamped
from threading import Thread
import time
from control_interfaces.srv import MoveP, MoveL
from interface_pkg.srv import MoveToJointPositions, WaistControl,AscendControl
import copy
from scipy.spatial.transform import Rotation as R
from scipy.spatial.transform import Slerp

# ================= 工具函数 =================
def pose_distance(p1: PoseStamped, p2: PoseStamped):
    dx = p1.pose.position.x - p2.pose.position.x
    dy = p1.pose.position.y - p2.pose.position.y
    dz = p1.pose.position.z - p2.pose.position.z
    return np.sqrt(dx*dx + dy*dy + dz*dz)

def quaternion_angle_diff(q1, q2):
    """
    q = geometry_msgs.msg.Quaternion
    return: rad
    """
    v1 = np.array([q1.x, q1.y, q1.z, q1.w])
    v2 = np.array([q2.x, q2.y, q2.z, q2.w])

    dot = np.abs(np.dot(v1, v2))
    dot = np.clip(dot, -1.0, 1.0)

    return 2 * np.arccos(dot)
def pose_to_matrix(pos, quat):
    """(pos, quat) -> 4x4 matrix"""
    x, y, z = pos
    qx, qy, qz, qw = quat

    R = np.array([
        [1 - 2*qy*qy - 2*qz*qz,  2*qx*qy - 2*qz*qw,      2*qx*qz + 2*qy*qw],
        [2*qx*qy + 2*qz*qw,      1 - 2*qx*qx - 2*qz*qz,  2*qy*qz - 2*qx*qw],
        [2*qx*qz - 2*qy*qw,      2*qy*qz + 2*qx*qw,      1 - 2*qx*qx - 2*qy*qy]
    ])

    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [x, y, z]
    return T


def matrix_to_pose(T):
    """4x4 matrix -> (pos, quat)"""
    x, y, z = T[:3, 3]
    R = T[:3, :3]

    tr = np.trace(R)
    if tr > 0:
        S = np.sqrt(tr + 1.0) * 2
        qw = 0.25 * S
        qx = (R[2,1] - R[1,2]) / S
        qy = (R[0,2] - R[2,0]) / S
        qz = (R[1,0] - R[0,1]) / S
    elif R[0,0] > R[1,1] and R[0,0] > R[2,2]:
        S = np.sqrt(1.0 + R[0,0] - R[1,1] - R[2,2]) * 2
        qw = (R[2,1] - R[1,2]) / S
        qx = 0.25 * S
        qy = (R[0,1] + R[1,0]) / S
        qz = (R[0,2] + R[2,0]) / S
    elif R[1,1] > R[2,2]:
        S = np.sqrt(1.0 + R[1,1] - R[0,0] - R[2,2]) * 2
        qw = (R[0,2] - R[2,0]) / S
        qx = (R[0,1] + R[1,0]) / S
        qy = 0.25 * S
        qz = (R[1,2] + R[2,1]) / S
    else:
        S = np.sqrt(1.0 + R[2,2] - R[0,0] - R[1,1]) * 2
        qw = (R[1,0] - R[0,1]) / S
        qx = (R[0,2] + R[2,0]) / S
        qy = (R[1,2] + R[2,1]) / S
        qz = 0.25 * S

    quat = np.array([qx, qy, qz, qw])
    quat /= np.linalg.norm(quat)

    return [x, y, z], quat.tolist()

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
# ================= ROS Node =================
class LiftClient(Node):
    def __init__(self):
        super().__init__("lift_client")
        self.cli = self.create_client(AscendControl, "/ascend_control")

        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Waiting for ascend_control service...")

    def send_request(self, pos, speed):
        req = AscendControl.Request()
        req.ascend_pos = pos
        req.ascend_speed = speed

        future = self.cli.call_async(req)
        rclpy.spin_until_future_complete(self, future)

        if future.result() is not None:
            return future.result()
        else:
            raise RuntimeError("Service call failed")

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

class PoseTransformTool(Node):
    def __init__(self):
        super().__init__('pose_transform_tool')
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.get_logger().info("Pose Transform Tool Ready.")

    def get_averaged_tf(self, target_frame, source_frame, samples=50, interval=0.05):
        """
        这里复用之前的核心均值滤波代码
        """
        collected_pos = []
        collected_quat = []
        
        self.get_logger().info(f"Sampling {samples} times: {source_frame} -> {target_frame}")
        
        count = 0
        while count < samples:
            try:
                t = self.tf_buffer.lookup_transform(target_frame, source_frame, rclpy.time.Time(), timeout=Duration(seconds=1.0))
                p = t.transform.translation
                q = t.transform.rotation
                collected_pos.append([p.x, p.y, p.z])
                collected_quat.append([q.x, q.y, q.z, q.w])
                count += 1
                time.sleep(interval)
            except Exception as e:
                self.get_logger().warning(f"Lookup failed: {e}")
                time.sleep(0.1)
                continue
        
        if not collected_pos: return None, None

        # 转换为numpy
        pos_array = np.array(collected_pos)
        quat_array = np.array(collected_quat)

        # 四元数对齐 (防止 +-q 问题)
        base_q = quat_array[0]
        for i in range(1, len(quat_array)):
            if np.dot(quat_array[i], base_q) < 0:
                quat_array[i] = -quat_array[i]

        # 去除异常值 (Mean +/- 2*Std)
        pos_mean = np.mean(pos_array, axis=0)
        pos_std = np.std(pos_array, axis=0)
        mask = np.all(np.abs(pos_array - pos_mean) < 2 * pos_std + 1e-6, axis=1) # +1e-6防止std为0
        
        filtered_pos = pos_array[mask]
        filtered_quat = quat_array[mask]
        
        if len(filtered_pos) == 0: return None, None

        final_pos = np.mean(filtered_pos, axis=0)
        avg_quat = np.mean(filtered_quat, axis=0)
        final_quat = avg_quat / np.linalg.norm(avg_quat)

        return list(final_pos), list(final_quat)

    def get_pose_in_base(self, base, marker, object_pose_marker):
        print("\n========== STEP 1: Marker → Base ==========")
        p,q = self.get_averaged_tf(base, marker)

        T_base_marker = pose_to_matrix(p, q)
        T_marker_object = pose_to_matrix(
            object_pose_marker["pos"],
            object_pose_marker["quat"]
        )

        # 物体在 base 下
        T_base_object = T_base_marker @ T_marker_object
        base_pos, base_quat = matrix_to_pose(T_base_object)

        print("Object pose in base_link:")
        print(f"  pos  = {np.round(base_pos, 4)}")
        print(f"  quat = {np.round(base_quat, 4)}")
        return T_base_object
    
    def get_pose_in_waist(self,T_base_object, waist, base):
        p,q = self.get_averaged_tf(base, waist)
        T_base_waist = pose_to_matrix(p, q)
        T_waist_object = np.linalg.inv(T_base_waist) @ T_base_object
        waist_pos, waist_quat = matrix_to_pose(T_waist_object)

        print("Object pose in waist_link:")
        print(f"  pos  = {np.round(waist_pos, 4)}")
        print(f"  quat = {np.round(waist_quat, 4)}")

        return self.create_pose_stamped(waist_pos, waist_quat, "waist_Link")
    def run(self, base, marker, waist, object_pose_marker):
        print("\n========== STEP 1: Marker → Base ==========")
        p,q = self.get_averaged_tf(base, marker)

        T_base_marker = pose_to_matrix(p, q)
        T_marker_object = pose_to_matrix(
            object_pose_marker["pos"],
            object_pose_marker["quat"]
        )

        # 物体在 base 下
        T_base_object = T_base_marker @ T_marker_object
        base_pos, base_quat = matrix_to_pose(T_base_object)

        print("Object pose in base_link:")
        print(f"  pos  = {np.round(base_pos, 4)}")
        print(f"  quat = {np.round(base_quat, 4)}")

        input("\n>>> Press [Enter] to compute pose in waist_link...")

        print("\n========== STEP 2: Base → Waist ==========")
        p,q = self.get_averaged_tf(base, waist)
        T_base_waist = pose_to_matrix(p, q)
        T_waist_object = np.linalg.inv(T_base_waist) @ T_base_object
        waist_pos, waist_quat = matrix_to_pose(T_waist_object)

        print("Object pose in waist_link:")
        print(f"  pos  = {np.round(waist_pos, 4)}")
        print(f"  quat = {np.round(waist_quat, 4)}")

        return (base_pos, base_quat), (waist_pos, waist_quat)

    def create_pose_stamped(self, p, q, frame_id):
        """ 辅助函数，将 p, q 封装为 PoseStamped """
        out = PoseStamped()
        out.header.frame_id = frame_id
        out.header.stamp = self.get_clock().now().to_msg()
        out.pose.position.x, out.pose.position.y, out.pose.position.z = p
        out.pose.orientation.x, out.pose.orientation.y, out.pose.orientation.z, out.pose.orientation.w = q
        return out


# ================= main =================

def main():
    rclpy.init()
    node = PoseTransformTool()
    movep_client = MovePClient()
    movel_client = MoveLClient()
    movej_client = MoveJointPositionsClient()
    waist_client = MoveWaistClient()
    lift_client = LiftClient()  
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    executor.add_node(movep_client)
    executor.add_node(movel_client)

    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()

    try:
        BASE = "base_link"
        MARKER = "camera_marker"
        WAIST = "waist_Link"

        # 🔴 你标定好的物体在 camera_marker 下的位姿
        OBJECT_POSE_IN_MARKER = {
            "pos":  [0.42650861067962254, -0.7154895787873785, 0.4418934385786957],
            "quat": [-0.40532737464659724, -0.2801290236289843, -0.6169523435722457, 0.6136833509583609]
        }
        # OBJECT_POSE_IN_MARKER = {
        #     "pos":  [-0.4112759356104786, 0.8525307419083551, 0.35893597214090145],
        #     "quat": [0.28252993821499195, 0.2657002179242719, -0.6433085712825326, 0.6601017424016193]
        # }
        # 
        T_base = node.get_pose_in_base(BASE, MARKER,OBJECT_POSE_IN_MARKER)
        left_init_pose = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        right_init_pose = [30.0, -61.0, 62.0, 90.0, 3.0, 63.0, -32.0]
        waist_client.send_request(90.0, 30)
        movej_client.send_request(left_init_pose, right_init_pose)
        # print("预备位完成")
        time.sleep(5)
        i = input("是否移动到预备位？")
        if i != 'y':
            return
        pose_in_waist = node.get_pose_in_waist(T_base, WAIST, BASE)
        print(pose_in_waist)
        pole_pose = copy.deepcopy(pose_in_waist)
        pole_pose.pose.position.x = 0.31
        pole_pose.pose.position.y = -0.65
        pole_pose.pose.position.z = 0.61
        if pose_distance(pole_pose, pose_in_waist) > 0.05 or pose_in_waist.pose.position.z > 0.67:
            print(pose_distance(pole_pose, pose_in_waist))
            print("pose error")
            i = input("go on ?")
            if i != 'y':
                return False
        if pose_in_waist.pose.position.z < 0.65:
            pose_in_waist = move_along_end_z(pose_in_waist, 0.65-pose_in_waist.pose.position.z)
            
        # ####  pos  = [ 0.8399 -0.5135  0.5154]
        # ####quat = [-0.2389 -0.0166  0.962  -0.1314]
        pose_in_waist2 = move_along_end_z(pose_in_waist, 0.08)
        movep_client.send_request(
            lor="right",
            pose=pose_in_waist2,
            to_frame="J7_right_Link",
            reference_frame="waist_Link",
            planner="ompl"
        )
        pos_threshold = 0.03        # 3 cm
        yaw_threshold = 3.0 * np.pi / 180.0
        wait = 0
        while True:
            wait += 1
            current_p, current_q = node.get_averaged_tf("waist_Link", "J7_right_Link", 5, 0.05)
            current_pose = node.create_pose_stamped(current_p, current_q, "waist_Link")
            pos_err = pose_distance(current_pose, pose_in_waist2)
            ang_err = quaternion_angle_diff(
                current_pose.pose.orientation,
                pose_in_waist2.pose.orientation
            )
            if pos_err < pos_threshold and ang_err < yaw_threshold:
                break
            if wait > 3000:
                return False
        print("moveP")
        i = input("是否移动到预备抓取位？")
        if i != 'y':
            return
        # way_points = []
        # way_points.append(copy.deepcopy(pose_in_waist2))
        # pose_in_waist = move_along_end_z(pose_in_waist2, -0.08)
        movep_client.send_request(
            lor="right",
            pose=pose_in_waist,
            to_frame="J7_right_Link",
            reference_frame="waist_Link",
            planner="ompl"
        )   

        # way_points.append(copy.deepcopy(pose_in_waist2))
        # way_points.append(pose_in_waist)

        # expanded = expand_pose_stamped_waypoints(way_points, 200)
        # pose_list = [p.pose for p in expanded]
        # movel_client.send_request(
        #     lor="right",
        #     waypoints=pose_list
        # )
        i = input("是否移动到抓取位？")
        if i != 'y':
            return
        lift_client.send_request(300.0, 30)
        i = input("是否后退位？")
        if i != 'y':
            return
        movej_client.send_request(left_init_pose, right_init_pose)

        waist_client.send_request(11.45, 30)
        lift_client.send_request(0.0, 30)


    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

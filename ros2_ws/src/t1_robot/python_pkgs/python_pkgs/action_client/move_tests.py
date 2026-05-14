import sys
sys.path.append("/workspaces/isaac_ros-dev/src/python_pkgs/python_pkgs") 
from action_client import MoveJClient, MovePClient, MoveLClient, GetJointClient, GetPoseClient, IKClient, HandClient
import cv2
import rclpy
from geometry_msgs.msg import PoseStamped, PointStamped, Pose
import time
import subprocess
from vision.yolo_dect import YOLOROS2Node, YoloClient
import copy
import time
import numpy as np
from math import acos, tan, pi
from tf_transformations import quaternion_from_matrix
from circular import *
from array import array
from scipy.spatial.transform import Rotation as R
from copy import deepcopy
from scipy.spatial.transform import Slerp

rclpy.init()

move_p_client = MovePClient()
hand_client = HandClient()
move_j_client = MoveJClient()
move_l_client = MoveLClient()
get_pose_client = GetPoseClient()
debug = False

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
        interp_pose_stamped.header = deepcopy(pose1.header)  # 继承 frame_id 和 stamp（也可以设置时间插值）

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

def expand_pose_stamped_waypoints(waypoints: list, steps_per_segment=10, angle_threshold_deg=1.0) -> list:
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


def move(motion_type, LoR, target, planner = None):
    if motion_type == "pose":
        success = move_p(LoR, target, planner)
    elif motion_type == "joint":
        success = move_j(LoR, target)
    if success:
        if motion_type == "pose":
            try:
                # time.sleep(0.5)
                success, current_pose = get_pose_client.send_request(LoR)
                pos_diff = np.array([
                current_pose.pose.position.x - target.pose.position.x,
                current_pose.pose.position.y - target.pose.position.y,
                current_pose.pose.position.z - target.pose.position.z
                ])
                euclidean_distance = np.linalg.norm(pos_diff)
                position_reached = euclidean_distance <= 0.05
                if position_reached:
                    if debug == True:
                        i = input("执行成功，是否执行下一步，输入c继续")
                        if i == "c":
                            return True
                        else:
                            return False
                    else:
                        return True
                else:
                    print("位置未达到，请检查")
                    print(euclidean_distance)
                    print(current_pose.pose)
                    print(target.pose)
                    i = input("c继续，s终止, r重试")
                    if i == "c":
                        return True
                    elif i == "s":
                        return False
                    elif i == "r":
                        while True:
                            if motion_type == "pose":
                                success = move_p(LoR, target, planner)
                            elif motion_type == "joint":
                                success = move_j(LoR, target)
                            if success:
                                break
                            else:
                                i = input("又执行失败，是否重试,r重试，其他取消")
                                if i == "r":
                                    continue
                                else:
                                    break
            except:
                print("查询失败")
                i = input("c继续，s终止, r重试")
                if i == "c":
                    return True
                elif i == "s":
                    return False
                elif i == "r":
                    while True:
                        if motion_type == "pose":
                            success = move_p(LoR, target, planner)
                        elif motion_type == "joint":
                            success = move_j(LoR, target)
                        if success:
                            break
                        else:
                            i = input("又执行失败，是否重试,r重试，其他取消")
                            if i == "r":
                                continue
                            else:
                                break
        elif motion_type == "joint":
            if debug == True:
                i = input("执行成功，是否执行下一步，输入c继续")
                if i == "c":
                    return True
                else:
                    return False
            else:
                return True
    else:
        print("执行失败")
        i = input("c继续，s终止,r重试")
        if i == "c":
            return True
        elif i == "s":
            return False
        elif i == "r":
            while True:
                if motion_type == "pose":
                    success = move_p(LoR, target, planner)
                elif motion_type == "joint":
                    success = move_j(LoR, target)
                if success:
                    break
                else:
                    i = input("又执行失败，是否重试,r重试，其他取消")
                    if i == "r":
                        continue
                    else:
                        break
            
def adjust_target_pose(obj_pose_base):
    """
    调整目标位置以补偿夹爪长度
    :param obj_pose_base: geometry_msgs/Pose 物体在基坐标系下的位姿
    :param gripper_quaternion: 夹爪姿态四元数 (x, y, z, w)
    :return: 调整后的手腕目标位姿 (geometry_msgs/Pose)
    """
    # 提取四元数分量 (ROS使用xyzw顺序)
    x = obj_pose_base.pose.orientation.x
    y = obj_pose_base.pose.orientation.y
    z = obj_pose_base.pose.orientation.z
    w = obj_pose_base.pose.orientation.w

    # 步骤4：构建旋转矩阵
    R = np.array([
        [1 - 2*y**2 - 2*z**2, 2*x*y - 2*w*z, 2*x*z + 2*w*y],
        [2*x*y + 2*w*z, 1 - 2*x**2 - 2*z**2, 2*y*z - 2*w*x],
        [2*x*z - 2*w*y, 2*y*z + 2*w*x, 1 - 2*x**2 - 2*y**2]
    ])

    # 步骤2：定义手腕坐标系下的偏移
    v_offset_wrist = np.array([-0.185, -0.03, 0.0])

    # 步骤5：转换到基坐标系
    v_offset_base = R.dot(v_offset_wrist)

    # 步骤6：计算修正后的目标位置
    adjusted_pose = PoseStamped()
    adjusted_pose.header.frame_id = obj_pose_base.header.frame_id
    adjusted_pose.pose.position.x = obj_pose_base.pose.position.x + v_offset_base[0]
    adjusted_pose.pose.position.y = obj_pose_base.pose.position.y + v_offset_base[1]
    adjusted_pose.pose.position.z = obj_pose_base.pose.position.z + v_offset_base[2]

    # 保持原始姿态（MoveIt会控制末端姿态）
    adjusted_pose.pose.orientation = obj_pose_base.pose.orientation

    return adjusted_pose

def move_p(lor, pose, planner):
    wait = 0
    retry = 0
    while True:
        if lor == "left":
            move_p_client.status = False
            success = move_p_client.send_goal(
                target_pose=pose,
                lor="left",
                to_frame="left_wrist_yaw_link",
                reference_frame="torso_link",
                planner=planner
            )
        else:
            move_p_client.status = False
            success = move_p_client.send_goal(
                target_pose=pose,
                lor="right",
                to_frame="right_wrist_yaw_link",
                reference_frame="torso_link",
                planner=planner
            )            
        # 等待移动完成
        while True:
            wait += 1
            # print("wait%f", wait)
            rclpy.spin_once(move_p_client, timeout_sec=0.1)
            if move_p_client.status == True:
                break
            if wait >= 100:
                # 可能丢包，重新发送请求
                break
        if move_p_client.success == True:
            retry = 0
            return True
        else:
            return False

def move_j(LoR, joints):
    wait = 0
    retry = 0
    while True:
        move_j_client.status = False
        success = move_j_client.send_goal(lor = LoR, target_joint_positions = joints)
                 
        # 等待移动完成
        while True:
            wait += 1
            rclpy.spin_once(move_j_client, timeout_sec=0.1)
            if move_j_client.status == True:
                break
            if wait >= 100:
                # 可能丢包，重新发送请求
                break
        if move_j_client.success == True:
            retry = 0
            return True
        else:
            return False

def main():
    planner = "cumotion"
    actions = 0
    while True:
        print(actions)
        print("movep_1")
        target_pose = PoseStamped()
        target_pose.header.frame_id = 'torso_link'
        target_pose.pose.position.x = 0.1
        target_pose.pose.position.y = 0.2
        target_pose.pose.position.z = 0.1
        target_pose.pose.orientation.w = 1.0  # 无旋转
        move("pose","left", target_pose, planner)
        actions += 1
        print("movep_2")
        target_pose.pose.position.y += 0.1
        target_pose.pose.position.x += 0.1
        move("pose","left", target_pose, planner)
        actions += 1
        print("put simple 1")
        left_joints = array('d', [0.436, 0.052, 0.035, 0.052, -0.052, -0.454, 0.0])
        right_joints = array('d', [-0.367, -0.506, 1.239, 0.035, -1.047, -0.471, -0.384])
        # right_joints = array('d', [-0.750, 0.122, 1.292, 0.105, -0.733, -0.0, 0.087])
        both_joints = left_joints + right_joints
        
        move("joint", "dual", both_joints)
        actions += 1
        print("put simple 2")
        right_joints = array('d', [-0.489, -0.611, 1.151, -0.366, -0.750, -0.332, 0.034])
        move("joint", "right", right_joints)
        actions += 1
        left_joints = array('d', [0.454, 0.017, 0.070, 0.052, -0.034, -0.471, -0.297])
        # move("joint", "left", left_joints)
        
    
    # target_joints = [-0.09330892562866211,0.06435918807983398,0.178566113114357,0.03957676887512207,-0.026129722595214844,-0.1746964454650879,0.08356237411499023,-0.03567337989807129,-0.002633020281791687,-0.05232071876525879,-0.09808111190795898,0.02737593650817871,0.04695144295692444,-0.04950296878814697]
    # move_j_client.status = False
    # move_j_client.send_goal(
    #     lor="dual",
    #     target_joint_positions = target_joints
    # )
    # while True:
    #     rclpy.spin_once(move_j_client)
    #     if move_j_client.status == True:
    #         break
    # left_p_pose = PoseStamped()
    # left_p_pose.header.frame_id = 'torso_link'
    # left_p_pose.pose.position.x = 0.2
    # left_p_pose.pose.position.y = 0.22
    # left_p_pose.pose.position.z = 0.09
    # left_p_pose.pose.orientation.x = 0.0
    # left_p_pose.pose.orientation.y = 0.0
    # left_p_pose.pose.orientation.z = 0.0
    # left_p_pose.pose.orientation.w = 1.0
    # success = move_p_client.send_goal(
    #     target_pose=left_p_pose,
    #     lor="left",
    #     to_frame="left_wrist_yaw_link",
    #     reference_frame="torso_link",
    #     planner="ompl"
    # )
    # target_pose = Pose()
    # target_pose.position.x = 0.2
    # target_pose.position.y = -0.22
    # target_pose.position.z = 0.09
    # target_pose.orientation.x = 0.0
    # target_pose.orientation.y = 0.0
    # target_pose.orientation.z = 0.0
    # target_pose.orientation.w = 1.0
    # right_p_pose = PoseStamped()
    # right_p_pose.header.frame_id = 'torso_link'
    # right_p_pose.pose = target_pose
    # start_time = time.time()
    # while True:
    #     move_p_client.status = False
    #     success = move_p_client.send_goal(
    #         target_pose=right_p_pose,
    #         lor="right",
    #         to_frame="right_wrist_yaw_link",
    #         reference_frame="torso_link",
    #         planner="cumotion"
    #     )
    #     # 等待移动完成
    #     while True:
    #         rclpy.spin_once(move_p_client)
    #         # rclpy.spin_once(detect_node)
    #         if move_p_client.status == True:
    #             # time.sleep(1)
    #             break
    #     if move_p_client.success == True:
    #         retry = 0
    #         break
    #     else:
    #         retry += 1
    #         if retry > 3:
    #             return False
    # # end_pose = Pose()
    # end_pose = copy.deepcopy(target_pose)
    # end_pose.position.z += 0.3

    # via_pose = copy.deepcopy(target_pose)
    # via_pose.position.z += 0.15
    # via_pose.position.y -= 0.2
    # waypoints = generate_arc_path(target_pose, via_pose, end_pose, tension=0.9)
    # # waypoints = []
    # # waypoints.append(copy.deepcopy(target_pose))
    # # target_pose.position.x += 0.1
    # # waypoints.append(copy.deepcopy(target_pose))
    # # target_pose.position.y -= 0.1
    # # waypoints.append(copy.deepcopy(target_pose))
    # # target_pose.position.z += 0.3
    # # waypoints.append(copy.deepcopy(target_pose))
    # # # print(waypoints)
    # move_l_client.send_goal(
    #     lor = "right",
    #     waypoints = waypoints
    # )
    # import matplotlib.pyplot as plt
    # # from mpl_toolkits.mplot3d import Axes3D

    # # fig = plt.figure()
    # # ax = fig.add_subplot(111, projection='3d')

    # # # 绘制轨迹
    # # xs = [p.position.x for p in waypoints]
    # # ys = [p.position.y for p in waypoints]
    # # zs = [p.position.z for p in waypoints]
    # # ax.plot(xs, ys, zs, 'b-', lw=2, label='B-Spline Path')

    # # # 标记控制点
    # # ax.scatter(target_pose.position.x, target_pose.position.y, target_pose.position.z, 
    # #            c='r', s=100, marker='o', label='Start')
    # # ax.scatter(via_pose.position.x, via_pose.position.y, via_pose.position.z, 
    # #            c='g', s=100, marker='^', label='Via Point')
    # # ax.scatter(end_pose.position.x, end_pose.position.y, end_pose.position.z, 
    # #            c='m', s=100, marker='s', label='End')
    # # ax.set_xlabel('X')
    # # ax.set_ylabel('Y')
    # # ax.set_zlabel('Z')
    # # plt.legend()
    # # plt.savefig("./fig.jpg")
    # fig = plt.figure(figsize=(8, 6))
    # ax = fig.add_subplot(111)

    # # 提取Y-Z坐标（假设所有X坐标相同）
    # fixed_x = target_pose.position.x  # 取起始点X值为固定坐标
    # ys = [p.position.y for p in waypoints]
    # zs = [p.position.z for p in waypoints]

    # # 绘制轨迹线
    # ax.plot(ys, zs, 'b-', lw=2, label='轨迹路径')
    
    # # 标记关键点（仅显示Y-Z坐标）
    # ax.scatter(target_pose.position.y, target_pose.position.z,
    #            c='r', s=100, marker='o', label='start (X={:.2f})'.format(fixed_x))
    # ax.scatter(via_pose.position.y, via_pose.position.z,
    #            c='g', s=100, marker='^', label='via')
    # ax.scatter(end_pose.position.y, end_pose.position.z,
    #            c='m', s=100, marker='s', label='end')

    # # 坐标轴设置
    # ax.set_xlabel('Y', fontsize=12)
    # ax.set_ylabel('Z', fontsize=12)
    # ax.set_title("Y-Z".format(fixed_x))
    # ax.grid(True, linestyle='--', alpha=0.7)
    
    # # 图例优化
    # ax.legend(loc='upper right', fontsize=10)
    
    # # 保存图像（调整dpi提升清晰度）
    # plt.savefig("./trajectory_2d.jpg")
    # plt.close()  # 防止内存泄漏
    
    # while True:
    #     rclpy.spin_once(move_l_client)
    #     if move_l_client.status == True:
    #         break
    # print(time.time() - start_time)

def move_l_test():
    p1 = PoseStamped()
    p1.header.frame_id = 'torso_link'
    p1.pose.position.x = 0.1
    p1.pose.position.y = 0.2
    p1.pose.position.z = 0.1
    p1.pose.orientation.w = 1.0  # 单位四元数

    # p2 = PoseStamped()
    # p2.header.frame_id = "base_link"
    # p2.pose.position.x = 0.2
    # p2.pose.position.y = 0.3
    # p2.pose.position.z = 0.1

    p2 = PoseStamped()
    p2.header.frame_id = "base_link"
    p2.pose.position.x = 0.2
    p2.pose.position.y = 0.3
    p2.pose.position.z = 0.1
    p2.pose.orientation.x = 0.707  # 180 度绕 Z 轴
    p2.pose.orientation.y = 0.0
    p2.pose.orientation.z = 0.0  # 180 度绕 Z 轴
    p2.pose.orientation.w = 0.707

    p3 = PoseStamped()
    p3.header.frame_id = 'torso_link'
    p3.pose.position.x = 0.1
    p3.pose.position.y = 0.2
    p3.pose.position.z = 0.1
    p3.pose.orientation.w = 1.0  # 单位四元数

    waypoints = [p1, p2, p3]

    # 插值扩展
    expanded = expand_pose_stamped_waypoints(waypoints, steps_per_segment=150)
    pose_list = [p.pose for p in expanded]
    move_l_client.send_goal(
        lor = "left",
        waypoints = pose_list
    )


if __name__ == '__main__':
    # main()
    move_l_test()
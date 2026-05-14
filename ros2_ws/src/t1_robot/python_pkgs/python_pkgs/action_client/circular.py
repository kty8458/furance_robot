import numpy as np
from geometry_msgs.msg import Pose
from math import acos, tan, pi
from tf_transformations import quaternion_from_matrix
from scipy.interpolate import BSpline
from scipy.spatial.transform import Rotation, Slerp



def generate_arc_path(start_pose, via_pose, end_pose, tension=0.5, num_points=100):
    """
    生成经过起始/终点、受途径点影响的B样条弧线
    :param tension: 张力系数 (0.0为直线，1.0为最大弯曲)
    :param num_points: 路径点数量
    :return: 包含路径点Pose的列表
    """
    # 提取坐标
    start = np.array([start_pose.position.x, start_pose.position.y, start_pose.position.z])
    via = np.array([via_pose.position.x, via_pose.position.y, via_pose.position.z])
    end = np.array([end_pose.position.x, end_pose.position.y, end_pose.position.z])

    # 计算中间控制点（根据张力调整）
    vec_se = end - start
    proj = np.dot(via - start, vec_se) / np.dot(vec_se, vec_se) 
    closest = start + proj * vec_se
    offset = via - closest
    adjusted_via = closest + tension * offset  # 关键张力控制逻辑

    # 构建B样条控制点 (二次曲线degree=2)
    control_points = np.stack([start, adjusted_via, end])
    degree = 2
    knots = np.array([0, 0, 0, 1, 1, 1])  # 确保曲线经过首尾点

    # 生成样条参数空间
    t = np.linspace(0, 1, num_points)
    spline = BSpline(knots, control_points, degree)

    # 姿态插值准备
    q_start = np.array([start_pose.orientation.x, start_pose.orientation.y,
                       start_pose.orientation.z, start_pose.orientation.w])
    q_end = np.array([end_pose.orientation.x, end_pose.orientation.y,
                     end_pose.orientation.z, end_pose.orientation.w])
    rotations = Rotation.from_quat([q_start, q_end])
    times = [0, 1]
    slerp = Slerp(times, rotations)
    waypoints = []
    for pos, t_val in zip(spline(t), t):
        # 位置插值
        pose = Pose()
        pose.position.x, pose.position.y, pose.position.z = pos
        
        # 姿态插值（球面线性插值）
        interpolated_rot = slerp(t_val)
        quat = interpolated_rot.as_quat()
        
        pose.orientation.x = quat[0]
        pose.orientation.y = quat[1]
        pose.orientation.z = quat[2]
        pose.orientation.w = quat[3]
        
        waypoints.append(pose)
    
    return waypoints

def rotation_matrix_from_axis_angle(axis_angle):
    """
    通过轴角生成旋转矩阵
    """
    angle = np.linalg.norm(axis_angle)
    if angle < 1e-6:
        return np.eye(3)
    
    axis = axis_angle / angle
    K = np.array([[0, -axis[2], axis[1]],
                  [axis[2], 0, -axis[0]],
                  [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(angle)*K + (1-np.cos(angle))*(K@K)

def interpolate_orientation(start_pose, end_pose, t):
    """
    四元数球面线性插值
    """
    q0 = np.array([start_pose.orientation.x, start_pose.orientation.y,
                   start_pose.orientation.z, start_pose.orientation.w])
    q1 = np.array([end_pose.orientation.x, end_pose.orientation.y,
                   end_pose.orientation.z, end_pose.orientation.w])
    
    dot = np.dot(q0, q1)
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    
    if dot > 0.9995:
        result = q0 + t*(q1 - q0)
        result /= np.linalg.norm(result)
        return compose_quaternion(*result)
    
    theta_0 = np.arccos(dot)
    sin_theta_0 = np.sin(theta_0)
    
    theta = theta_0 * t
    sin_theta = np.sin(theta)
    
    s0 = np.cos(theta) - dot * sin_theta / sin_theta_0
    s1 = sin_theta / sin_theta_0
    
    interpolated = s0*q0 + s1*q1
    return compose_quaternion(*interpolated)

def compose_quaternion(x, y, z, w):
    q = Pose().orientation
    q.x, q.y, q.z, q.w = x, y, z, w
    return q
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from control_interfaces.action import MoveP
from geometry_msgs.msg import PoseStamped
import time
import math
import numpy as np
from geometry_msgs.msg import PoseStamped



class MovePClient(Node):
    def __init__(self):
        super().__init__('move_p_test_client')
        self._action_client = ActionClient(self, MoveP, 'move_p')
        self.status = False
        self.success =False

    def send_goal(self,         
        target_pose: PoseStamped,
        lor: str,
        to_frame: str,
        reference_frame: str):
        goal_msg = MoveP.Goal()
        goal_msg.target_pose = target_pose
        goal_msg.lor = lor
        goal_msg.to_frame = to_frame
        goal_msg.reference_frame = reference_frame

        self.get_logger().info(f'发送目标: pose={target_pose}, lor={lor}, to_frame={to_frame}, reference_frame={reference_frame}')
        self._action_client.wait_for_server()

        self._send_goal_future = self._action_client.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback
        )
        self.get_logger().info(f'wait call back')
        success = self._send_goal_future.add_done_callback(self.goal_response_callback)
        return success

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().info('目标被拒绝')
            return

        self.get_logger().info('目标已接受，等待结果...')
        self._get_result_future = goal_handle.get_result_async()
        success = self._get_result_future.add_done_callback(self.get_result_callback)
        return success

    def get_result_callback(self, future):
        result = future.result().result
        success = result.success

        if success:  # SUCCEEDED
            self.get_logger().info(f'操作成功')
            self.success = True
            
        else:
            self.get_logger().info(f'操作失败')
            self.success = False
        self.status = True   
        return success

    def feedback_callback(self, feedback_msg):
        feedback = feedback_msg.feedback
        self.get_logger().info(f'反馈信息：{feedback.feedback_message}')

    def rot_z(self, initial_q, angle):
        w0, x0, y0, z0 = initial_q

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
    
    def adjust_target_pose(self, obj_pose_base):
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
        v_offset_wrist = np.array([-0.2, 0.0, 0.0])

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


def main():
    print("new_client start3")
    rclpy.init()
    global client
    client = MovePClient()
    # print("new_c33")
    
    # executor = MultiThreadedExecutor()
    # executor.add_node(client)
    # spin_t = threading.Thread(target=executor.spin, daemon=True)
    # spin_t.start()
    
    # 同步调用
    target_pose = PoseStamped()
    target_pose.header.frame_id = 'torso_link'
    target_pose.pose.position.x = 0.3
    target_pose.pose.position.y = -0.1
    target_pose.pose.position.z = 0.1
    target_pose.pose.orientation.w = 1.0  # 无旋转

    client.status = False
    success = client.send_goal(
        target_pose=target_pose,
        lor="right",
        to_frame="right_wrist_yaw_link"
    )
    print(success)
    while True:
        rclpy.spin_once(client)
        if client.status == True:
            # time.sleep(1)
            break
        
    target_pose.pose.position.x = 0.2
    client.send_goal(
        target_pose=target_pose,
        lor="right",
        to_frame="right_wrist_yaw_link"
    )
    rclpy.spin(client)
    
    # rclpy.spin(client)

    
    # target_pose.pose.position.x = 0.2
    
    # client.send_goal_sync(
    #     target_pose=target_pose,
    #     lor="right",
    #     to_frame="right_wrist_yaw_link",
    #     timeout_sec=80.0
    # )

    # rclpy.shutdown()

if __name__ == '__main__':
    main()
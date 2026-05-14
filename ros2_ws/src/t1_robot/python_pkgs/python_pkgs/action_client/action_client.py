from typing import Optional, Tuple
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from control_interfaces.action import MoveP, MoveJ, MoveL, HandAction
from control_interfaces.srv import ComputeIk, GetJoint, GetPose, ExecuteTrajectory
from geometry_msgs.msg import PoseStamped
import time
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32
from trajectory_msgs.msg import JointTrajectory

class TrajClient(Node):
    def __init__(self):
        super().__init__('traj_client')
        self.cli = self.create_client(ExecuteTrajectory, 'execute_trajectory')
        while not self.cli.wait_for_service(timeout_sec=1.0):
            self.get_logger().info('service not available, waiting...')
        self.req = ExecuteTrajectory.Request()

    def send_trajectory(self, traj: JointTrajectory):
        self.req.trajectory = traj
        future = self.cli.call_async(self.req)
        rclpy.spin_until_future_complete(self, future)
        if future.result():
            print(f"[Client] Call success: {future.result().success}, msg: {future.result().message}")
            return True
        else:
            print("[Client] Call failed")
            return False

class WaistPublisher(Node):
    def __init__(self):
        super().__init__('float_publisher_node')
        self.publisher_ = self.create_publisher(Float32, 'turn_waist', 10)

    def publish_once(self, value: float):
        msg = Float32()
        msg.data = value / 180 * 3.1415926
        self.publisher_.publish(msg)
        self.get_logger().info(f'Published: {msg.data}')

class HandClient(Node):
    def __init__(self):
        super().__init__('hand_action_client')
        self._client = ActionClient(self, HandAction, '/hand_control')

    def send_command(self, hand, angles, velocity=None, command=""):
        # 构造 goal
        goal_msg = HandAction.Goal()
        goal_msg.hand = hand
        goal_msg.command = command
        goal_msg.angles = angles
        if velocity:
            goal_msg.velocity = velocity

        # 等待 action server
        if not self._client.wait_for_server(timeout_sec=1.0):
            self.get_logger().error('Action server not available')
            return

        # 异步发送，不等待 goal response 或 result
        future = self._client.send_goal_async(goal_msg)
        self.get_logger().info(f"Goal sent to {hand} hand.")
        time.sleep(0.2)

class VelocityController(Node):
    def __init__(self, linear_x=0.0, linear_y=0.0, angular_z=0.0, rate=10.0):
        """速度控制器
        
        Args:
            linear_x (float): 线速度 (m/s)
            angular_z (float): 角速度 (rad/s)
            rate (float): 发布频率 (Hz)
        """
        super().__init__('velocity_controller')
        self._publisher = self.create_publisher(Twist, 'cmd_vel', 10)
        self._timer = None
        self._active = False
        
        # 速度参数
        self.linear_x = linear_x
        self.linear_y = linear_y
        self.angular_z = angular_z
        self.rate = rate
        
        self.get_logger().info("速度控制器已初始化")
    
    def set_velocity(self, linear_x=None, linear_y=None, angular_z=None, rate=None):
        """设置速度参数
        
        Args:
            linear_x (float): 新线速度 (不修改则保持原值)
            angular_z (float): 新角速度 (不修改则保持原值)
            rate (float): 新发布频率 (不修改则保持原值)
        """
        if linear_x is not None:
            self.linear_x = linear_x
        if linear_y is not None:
            self.linear_y = linear_y
        if angular_z is not None:
            self.angular_z = angular_z
        if rate is not None:
            self.rate = rate
        
        # 如果正在运行，则重启定时器以应用新频率
        if self._active and self._timer:
            self.stop()
            self.start()
        
        self.get_logger().info(
            f"速度设置: 线速度={self.linear_x:.2f} m/s, "
            f"角速度={self.angular_z:.2f} rad/s, "
            f"频率={self.rate:.1f} Hz"
        )
    
    def start(self):
        """开始发送速度指令"""
        if self._active:
            self.get_logger().warn("速度指令已在发送中")
            return
        
        self._active = True
        
        # 创建定时器
        timer_period = 1.0 / self.rate
        self._timer = self.create_timer(timer_period, self._publish_callback)
        self.get_logger().info("开始发送速度指令")
    
    def stop(self):
        """停止发送速度指令"""
        if not self._active:
            self.get_logger().warn("速度指令未在发送")
            return
        
        self._active = False
        
        # 销毁定时器并发送零速
        if self._timer:
            self._timer.cancel()
            self._timer = None
        
        # 发送停止指令
        self._publish_zero_velocity()
        self.get_logger().info("已停止发送速度指令")
    
    def _publish_callback(self):
        """定时器回调函数：发布速度指令"""
        if not self._active:
            return
        twist = Twist()
        twist.linear.x = self.linear_x
        twist.linear.y = self.linear_y
        twist.angular.z = self.angular_z
        self._publisher.publish(twist)
    
    def _publish_zero_velocity(self):
        """发布零速度指令"""
        twist = Twist()
        twist.linear.x = 0.0
        twist.linear.y = 0.0
        twist.angular.z = 0.0
        self._publisher.publish(twist)
    
    def send_once(self):
        """单次发送当前速度指令"""
        if self._active:
            self.get_logger().warn("已处于持续发送模式，无法单次发送")
            return
        
        self._publish_callback()
        self.get_logger().info("单次发送速度指令完成")

class IKClient(Node):
    def __init__(self):
        super().__init__('ik_compute_client')
        self.client = self.create_client(ComputeIk, '/compute_ik')
        self.client.wait_for_service(timeout_sec=10.0)
    
    def send_request(self, target_pose, lor, to_frame, reference_frame):
        """直接参数传递接口
        
        Args:
            target_pose (PoseStamped): 完整的目标位姿
            lor (str): 'left'或'right'
            to_frame (str): 末端执行器坐标系
            reference_frame (str): 参考坐标系
        
        Returns:
            tuple: (success, joint_angles)
        """
        req = ComputeIk.Request()
        req.target_pose = target_pose
        req.lor = lor
        req.to_frame = to_frame
        req.reference_frame = reference_frame
        
        future = self.client.call_async(req)
        start_time = time.time()
        while rclpy.ok() and not future.done():
            rclpy.spin_once(self, timeout_sec=0.1)
            elapsed = time.time() - start_time
            if elapsed > 5.0:
                self.get_logger().error(f"服务调用超时 (5 秒), Future 状态: done={future.done()}, cancelled={future.cancelled()}")
                future.cancel()
                return False, []
        if future.done():
            try:
                response = future.result()
                return response.success, response.joint_angles
            except Exception as e:
                self.get_logger().error(f'服务错误: {str(e)}')
                return False, []
        return False, []

class GetJointClient(Node):
    def __init__(self):
        super().__init__('get_joint_client')
        self.client = self.create_client(GetJoint, '/get_joint')
        self.client.wait_for_service(timeout_sec=10.0)
    
    def send_request(self, lor):
        req = GetJoint.Request()
        req.lor = lor
        
        future = self.client.call_async(req)
        # result = rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        start_time = time.time()
        while rclpy.ok() and not future.done():
            rclpy.spin_once(self, timeout_sec=0.1)
            elapsed = time.time() - start_time
            if elapsed > 5.0:
                self.get_logger().error(f"服务调用超时 (5 秒), Future 状态: done={future.done()}, cancelled={future.cancelled()}")
                future.cancel()
                return False, []
        if future.done():
            try:
                response = future.result()
                return response.success, response.joint_angles
            except Exception as e:
                self.get_logger().error(f'服务错误: {str(e)}')
                return False, []
        return False, []

class GetPoseClient(Node): 
    def __init__(self):
        super().__init__('get_pose_client')
        self.client = self.create_client(GetPose, '/get_pose')
        self.client.wait_for_service(timeout_sec=10.0)
    
    def send_request(self, lor):
        req = GetPose.Request()
        req.lor = lor
        
        future = self.client.call_async(req)
        # result = rclpy.spin_until_future_complete(self, future)
        start_time = time.time()
        while rclpy.ok() and not future.done():
            rclpy.spin_once(self, timeout_sec=0.1)
            elapsed = time.time() - start_time
            if elapsed > 5.0:
                self.get_logger().error(f"服务调用超时 (5 秒), Future 状态: done={future.done()}, cancelled={future.cancelled()}")
                future.cancel()
                return False, []
        if future.done():
            try:
                response = future.result()
                return response.success, response.target_pose
            except Exception as e:
                self.get_logger().error(f'服务错误: {str(e)}')
                return False, []
        return False, []

class BaseMoveClient(Node):
    def __init__(self, node_name, action_name):
        super().__init__(node_name)
        self._action_client = ActionClient(self, self._get_action_type(), action_name)
        self.status = False
        self.success = False

    def _get_action_type(self):
        # 抽象方法由子类实现
        raise NotImplementedError

    def send_goal(self, **kwargs):
        goal_msg = self._create_goal_msg(**kwargs)
        self._action_client.wait_for_server()
        
        self._send_goal_future = self._action_client.send_goal_async(
            goal_msg, 
            feedback_callback=self.feedback_callback
        )
        self._send_goal_future.add_done_callback(self.goal_response_callback)

    def _create_goal_msg(self, **kwargs):
        # 由子类实现具体goal构造逻辑
        raise NotImplementedError

    def feedback_callback(self, feedback_msg):
        # 可提供默认反馈处理，子类可选重写
        self.get_logger().debug(f'Feedback: {feedback_msg}')

    def goal_response_callback(self, future):
        # 统一响应处理（可复用）
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('Goal rejected')
            return

        self._get_result_future = goal_handle.get_result_async()
        self._get_result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        # 统一结果处理模板
        result = future.result().result
        self.success = result.success
        self.status = True
        self._handle_specific_result(result)  # 子类扩展点

    def _handle_specific_result(self, result):
        # 子类实现具体结果处理
        pass
        

class MovePClient(BaseMoveClient):
    def __init__(self):
        super().__init__('move_p_client', 'move_p')
        
    def _get_action_type(self):
        return MoveP

    def _create_goal_msg(self, target_pose, lor, to_frame, reference_frame, planner):
        goal_msg = MoveP.Goal()
        goal_msg.target_pose = target_pose
        goal_msg.lor = lor
        goal_msg.to_frame = to_frame
        goal_msg.reference_frame = reference_frame
        goal_msg.planner = planner
        return goal_msg

    def _handle_specific_result(self, result):
        if self.success:
            self.get_logger().info(f"MoveP成功")

class MoveJClient(BaseMoveClient):
    def __init__(self):
        super().__init__('move_j_client', 'move_j')

    def _get_action_type(self):
        return MoveJ

    def _create_goal_msg(self, lor, target_joint_positions):
        goal_msg = MoveJ.Goal()
        goal_msg.target_joint_positions = target_joint_positions
        goal_msg.lor = lor
        return goal_msg
    
class MoveLClient(BaseMoveClient):
    def __init__(self):
        super().__init__('move_l_client', 'move_l')

    def _get_action_type(self):
        return MoveL

    def _create_goal_msg(self, lor, waypoints):
        goal_msg = MoveL.Goal()
        goal_msg.waypoints = waypoints
        goal_msg.lor = lor
        return goal_msg

def main():
    print("new_client start2")
    rclpy.init()
    client = MovePClient()

    # 同步调用
    target_pose = PoseStamped()
    target_pose.header.frame_id = 'torso_link'
    target_pose.pose.position.x = 0.3
    target_pose.pose.position.y = -0.1
    target_pose.pose.position.z = 0.1
    target_pose.pose.orientation.w = 1.0  # 无旋转


    client.send_goal_sync(
        target_pose=target_pose,
        lor="right",
        to_frame="right_wrist_yaw_link",
        timeout_sec=80.0
    )

    time.sleep(3)
    
    # target_pose.pose.position.x = 0.2
    
    # client.send_goal_sync(
    #     target_pose=target_pose,
    #     lor="right",
    #     to_frame="right_wrist_yaw_link",
    #     timeout_sec=80.0
    # )

    rclpy.shutdown()

if __name__ == '__main__':
    main()
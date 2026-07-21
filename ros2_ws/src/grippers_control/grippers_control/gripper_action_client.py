import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node

from control_interfaces.action import GripperAction   # 替换为你的包名


class GripperActionClient(Node):

    def __init__(self):
        super().__init__("gripper_action_client")
        self._client = ActionClient(self, GripperAction, "gripper_action")
        self._gripper_feedback = ""
        self._gripper_status = "idle"
        self._sync_result_future = None

    def send_goal(self, arm: str, method: str, torque: float, position: float):
        """
        异步发送 GripperAction Goal
        """
        # 等待 action server 启动
        if not self._client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("Action server not available!")
            return None

        goal_msg = GripperAction.Goal()
        goal_msg.arm = arm
        goal_msg.method = method
        goal_msg.torque = torque
        goal_msg.position = position

        self.get_logger().info(f"Sending goal: {goal_msg}")

        self._sync_result_future = rclpy.task.Future()

        # 发送目标
        send_goal_future = self._client.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback
        )

        send_goal_future.add_done_callback(self.goal_response_callback)
        rclpy.spin_until_future_complete(self, self._sync_result_future)
        return self._sync_result_future.result()

    def feedback_callback(self, feedback_msg):
        fb = feedback_msg.feedback
        self.get_logger().info(
            f"[Feedback] pos={fb.current_position:.3f}, "
            f"status={fb.gripper_status}, msg={fb.gripper_message}"
        )
    
    def goal_response_callback(self, future):
        goal_handle = future.result()
        # self._current_nav_goal_handle = goal_handle  # 保存句柄

        if not goal_handle.accepted:
            self.get_logger().warn("[GRIPPER] Goal rejected")
            self._gripper_status = "failed"
            return

        self.get_logger().info("[GRIPPER] Goal accepted")
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.goal_result_callback)

    def goal_result_callback(self, future):
        result = future.result().result

        if result.success:
            self._gripper_status = "completed"
            self._gripper_feedback = "completed"
            self.get_logger().info("[GRIPPER] Completed successfully")
        else:
            self._gripper_status = "failed"
            self._gripper_feedback = "failed"
            self.get_logger().warn("[GRIPPER] Failed")
        
        if self._sync_result_future is not None:
            self._sync_result_future.set_result(result)

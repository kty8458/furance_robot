import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from trajectory_msgs.msg import JointTrajectoryPoint
from control_msgs.action import FollowJointTrajectory
from sensor_msgs.msg import JointState
import time
import threading


class SimArmController(Node):
    def __init__(self):
        super().__init__("sim_arm_controller")

        self.left_action_server = ActionServer(
            self,
            FollowJointTrajectory,
            "/left_arm_controller/follow_joint_trajectory",
            execute_callback=self.execute_left,
            goal_callback=self.handle_goal,
            cancel_callback=self.handle_cancel,
        )

        self.right_action_server = ActionServer(
            self,
            FollowJointTrajectory,
            "/right_arm_controller/follow_joint_trajectory",
            execute_callback=self.execute_right,
            goal_callback=self.handle_goal,
            cancel_callback=self.handle_cancel,
        )

        self.both_action_server = ActionServer(
            self,
            FollowJointTrajectory,
            "/both_arm_controller/follow_joint_trajectory",
            execute_callback=self.execute_both,
            goal_callback=self.handle_goal,
            cancel_callback=self.handle_cancel,
        )

        self.sim_joint_pub = self.create_publisher(JointState, '/sim_joint_commands', 10)

        self.left_busy = False
        self.right_busy = False
        self.both_busy = False

        self.get_logger().info("SimArmController started.")

    def handle_goal(self, goal_request):
        return GoalResponse.ACCEPT

    def handle_cancel(self, goal_handle):
        self.get_logger().info("Received cancel request.")
        return CancelResponse.ACCEPT

    def publish_sim_joints(self, joint_names, positions):
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.name = list(joint_names)
        js.position = list(positions)
        self.sim_joint_pub.publish(js)

    def execute_trajectory(self, goal_handle, arm_side):
        self.get_logger().info(f"Executing {arm_side} arm trajectory (sim)...")
        result = FollowJointTrajectory.Result()

        trajectory = goal_handle.request.trajectory
        joint_names = trajectory.joint_names

        prev_time = 0.0
        for point in trajectory.points:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.get_logger().info(f"{arm_side} arm goal canceled.")
                return result

            # Wait according to trajectory timing
            current_time = point.time_from_start.sec + point.time_from_start.nanosec * 1e-9
            dt = current_time - prev_time
            if dt > 0:
                time.sleep(dt)
            prev_time = current_time

            # Publish the current trajectory point as sim joint command
            self.publish_sim_joints(joint_names, point.positions)

        goal_handle.succeed()
        self.get_logger().info(f"{arm_side} arm sim trajectory complete.")
        return result

    def execute_left(self, goal_handle):
        self.left_busy = True
        try:
            return self.execute_trajectory(goal_handle, "LEFT")
        finally:
            self.left_busy = False

    def execute_right(self, goal_handle):
        self.right_busy = True
        try:
            return self.execute_trajectory(goal_handle, "RIGHT")
        finally:
            self.right_busy = False

    def execute_both(self, goal_handle):
        self.both_busy = True
        try:
            return self.execute_trajectory(goal_handle, "BOTH")
        finally:
            self.both_busy = False


def main(args=None):
    rclpy.init(args=args)
    node = SimArmController()
    executor = rclpy.executors.MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

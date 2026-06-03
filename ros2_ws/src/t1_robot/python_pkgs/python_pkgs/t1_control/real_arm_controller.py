import math
import time
import threading

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from rclpy.callback_groups import ReentrantCallbackGroup

from control_msgs.action import FollowJointTrajectory
from sensor_msgs.msg import JointState
from interface_pkg.srv import MoveToJointPositions


LEFT_JOINT_NAMES = [f'ARM-L-J{i}_Joint' for i in range(1, 8)]
RIGHT_JOINT_NAMES = [f'ARM-R-J{i}_Joint' for i in range(1, 8)]

# 位置到达阈值（弧度），所有关节均在此范围内认为到位
POSITION_THRESHOLD = 0.05  # ~2.9°
# 单个 waypoint 等待到位的超时（秒） — 大角度运动需要更长时间
WAYPOINT_TIMEOUT = 60.0
# 到位检查轮询间隔
POLL_INTERVAL = 0.1


class RealArmController(Node):
    """将 MoveIt FollowJointTrajectory action 转发到真机的 /move_joint_positions 服务.

    逐 waypoint 下发，每帧发送后等待机械臂实际到位（通过 /joint_states 反馈验证）
    再发送下一帧，避免一口气发完导致机械臂跟不上。
    """

    def __init__(self):
        super().__init__("real_arm_controller")

        self._cb_group = ReentrantCallbackGroup()

        self._move_client = self.create_client(
            MoveToJointPositions, '/move_joint_positions',
            callback_group=self._cb_group,
        )

        self._js_lock = threading.Lock()
        self._left_current = [0.0] * 7
        self._right_current = [0.0] * 7
        self.create_subscription(
            JointState, '/joint_states', self._joint_states_cb, 10,
            callback_group=self._cb_group,
        )

        self.left_action_server = ActionServer(
            self, FollowJointTrajectory,
            "/left_arm_controller/follow_joint_trajectory",
            execute_callback=self.execute_left,
            goal_callback=self.handle_goal,
            cancel_callback=self.handle_cancel,
            callback_group=self._cb_group,
        )
        self.right_action_server = ActionServer(
            self, FollowJointTrajectory,
            "/right_arm_controller/follow_joint_trajectory",
            execute_callback=self.execute_right,
            goal_callback=self.handle_goal,
            cancel_callback=self.handle_cancel,
            callback_group=self._cb_group,
        )
        self.both_action_server = ActionServer(
            self, FollowJointTrajectory,
            "/both_arm_controller/follow_joint_trajectory",
            execute_callback=self.execute_both,
            goal_callback=self.handle_goal,
            cancel_callback=self.handle_cancel,
            callback_group=self._cb_group,
        )

        self._cancelled = False

        self.get_logger().info("RealArmController started, waiting for /move_joint_positions...")

    def handle_goal(self, goal_request):
        return GoalResponse.ACCEPT

    def handle_cancel(self, goal_handle):
        self.get_logger().info("Received cancel request.")
        self._cancelled = True
        return CancelResponse.ACCEPT

    def _joint_states_cb(self, msg: JointState):
        with self._js_lock:
            for name, pos in zip(msg.name, msg.position):
                if name in LEFT_JOINT_NAMES:
                    self._left_current[LEFT_JOINT_NAMES.index(name)] = pos
                elif name in RIGHT_JOINT_NAMES:
                    self._right_current[RIGHT_JOINT_NAMES.index(name)] = pos

    def _snapshot_current(self):
        with self._js_lock:
            return list(self._left_current), list(self._right_current)

    def _send_move(self, left_rad, right_rad):
        """阻塞调用 /move_joint_positions."""
        if not self._move_client.service_is_ready():
            if not self._move_client.wait_for_service(timeout_sec=2.0):
                self.get_logger().warn("/move_joint_positions service unavailable")
                return False

        req = MoveToJointPositions.Request()
        req.left_joints = [float(math.degrees(a)) for a in left_rad]
        req.right_joints = [float(-math.degrees(a)) for a in right_rad]
        left_str = '[' + ', '.join(f'{v:7.2f}' for v in req.left_joints) + ']'
        right_str = '[' + ', '.join(f'{v:7.2f}' for v in req.right_joints) + ']'
        self.get_logger().info(f"send_move L(deg)={left_str} R(deg)={right_str}")

        future = self._move_client.call_async(req)
        start = time.monotonic()
        while not future.done():
            if time.monotonic() - start > 5.0:
                self.get_logger().warn("move_joint_positions call timed out")
                return False
            time.sleep(0.01)
        return True

    def _is_reached(self, target_left, target_right):
        """检查当前关节位置是否已到达目标."""
        left_now, right_now = self._snapshot_current()
        for i in range(7):
            if abs(left_now[i] - target_left[i]) > POSITION_THRESHOLD:
                return False
            if abs(right_now[i] - target_right[i]) > POSITION_THRESHOLD:
                return False
        return True

    def _wait_for_position(self, target_left, target_right, timeout=WAYPOINT_TIMEOUT):
        """等待机械臂到达目标位置，返回是否成功."""
        start = time.monotonic()
        while not self._is_reached(target_left, target_right):
            if self._cancelled:
                return False
            if time.monotonic() - start > timeout:
                left_now, right_now = self._snapshot_current()
                self.get_logger().warn(
                    f"Waypoint timeout after {timeout}s, diff: "
                    f"L={[f'{abs(a-b):.3f}' for a, b in zip(left_now, target_left)]} "
                    f"R={[f'{abs(a-b):.3f}' for a, b in zip(right_now, target_right)]}"
                )
                return False
            time.sleep(POLL_INTERVAL)
        return True

    def execute_trajectory(self, goal_handle, arm_side):
        """逐 waypoint 下发，每帧等待到位后再发下一帧."""
        self.get_logger().info(f"Executing {arm_side} arm trajectory (real)...")
        self._cancelled = False
        result = FollowJointTrajectory.Result()

        trajectory = goal_handle.request.trajectory
        joint_names = list(trajectory.joint_names)

        # 本侧关节在 trajectory.joint_names 中的索引映射
        left_idx_map = {LEFT_JOINT_NAMES.index(n): i
                        for i, n in enumerate(joint_names) if n in LEFT_JOINT_NAMES}
        right_idx_map = {RIGHT_JOINT_NAMES.index(n): i
                         for i, n in enumerate(joint_names) if n in RIGHT_JOINT_NAMES}

        for point_idx, point in enumerate(trajectory.points):
            if self._cancelled or goal_handle.is_cancel_requested:
                result.error_code = FollowJointTrajectory.Result.PATH_TOLERANCE_VIOLATED
                goal_handle.canceled()
                self.get_logger().info(f"{arm_side} arm goal canceled.")
                return result

            # 构建本帧左右臂目标
            left_target, right_target = self._snapshot_current()
            positions = list(point.positions)
            for j_idx, p_idx in left_idx_map.items():
                left_target[j_idx] = positions[p_idx]
            for j_idx, p_idx in right_idx_map.items():
                right_target[j_idx] = positions[p_idx]

            # 执行单臂时，未执行侧保持当前值不动
            if arm_side == "LEFT":
                _, right_target = self._snapshot_current()
            elif arm_side == "RIGHT":
                left_target, _ = self._snapshot_current()

            self.get_logger().info(
                f"Waypoint {point_idx + 1}/{len(trajectory.points)}")
            self._send_move(left_target, right_target)

            # 等待机械臂实际到位（最后一帧也等待，确保最终位姿准确）
            if not self._wait_for_position(left_target, right_target):
                if self._cancelled:
                    result.error_code = FollowJointTrajectory.Result.PATH_TOLERANCE_VIOLATED
                    goal_handle.canceled()
                    self.get_logger().warn(f"{arm_side} arm canceled while waiting for position.")
                    return result
                # 超时但不取消，继续下一个 waypoint（机械臂可能已经接近）
                self.get_logger().warn(f"Waypoint {point_idx + 1} not fully reached, continuing...")

        if self._cancelled:
            result.error_code = FollowJointTrajectory.Result.PATH_TOLERANCE_VIOLATED
            goal_handle.canceled()
            return result

        goal_handle.succeed()
        self.get_logger().info(f"{arm_side} arm real trajectory complete.")
        return result

    def execute_left(self, goal_handle):
        try:
            return self.execute_trajectory(goal_handle, "LEFT")
        finally:
            self._cancelled = False

    def execute_right(self, goal_handle):
        try:
            return self.execute_trajectory(goal_handle, "RIGHT")
        finally:
            self._cancelled = False

    def execute_both(self, goal_handle):
        try:
            return self.execute_trajectory(goal_handle, "BOTH")
        finally:
            self._cancelled = False


def main(args=None):
    rclpy.init(args=args)
    node = RealArmController()
    executor = rclpy.executors.MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

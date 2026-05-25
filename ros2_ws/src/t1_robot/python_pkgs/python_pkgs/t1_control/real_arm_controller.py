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

# 10 Hz 控制周期
CONTROL_PERIOD = 0.1


class RealArmController(Node):
    """将 MoveIt FollowJointTrajectory action 转发到真机的 /move_joint_positions 服务.

    与 sim_arm_controller 对应的硬件版本。
    - 以 10Hz 频率向 /move_joint_positions 发送插值后的当前目标点（双臂同时下发）
    - 订阅 /joint_states 缓存最新的左右臂角度，执行单臂动作时未执行的一侧用当前角度填充，
      避免另一只手臂被错误归零
    - 输入轨迹点为弧度，下发服务为角度（service 注释为弧度但实际接口约定为度）
    """

    def __init__(self):
        super().__init__("real_arm_controller")

        self._cb_group = ReentrantCallbackGroup()

        # /move_joint_positions 客户端
        self._move_client = self.create_client(
            MoveToJointPositions, '/move_joint_positions',
            callback_group=self._cb_group,
        )

        # /joint_states 订阅 — 缓存当前左右臂角度
        self._js_lock = threading.Lock()
        self._left_current = [0.0] * 7
        self._right_current = [0.0] * 7
        self.create_subscription(
            JointState, '/joint_states', self._joint_states_cb, 10,
            callback_group=self._cb_group,
        )

        # action servers
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

        self.left_busy = False
        self.right_busy = False
        self.both_busy = False

        self.get_logger().info("RealArmController started, waiting for /move_joint_positions...")

    def handle_goal(self, goal_request):
        return GoalResponse.ACCEPT

    def handle_cancel(self, goal_handle):
        self.get_logger().info("Received cancel request.")
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
        """向真机服务下发一帧目标位置（输入弧度，转换为度）."""
        if not self._move_client.service_is_ready():
            if not self._move_client.wait_for_service(timeout_sec=1.0):
                self.get_logger().warn("/move_joint_positions service unavailable, skipping frame")
                return False

        req = MoveToJointPositions.Request()
        req.left_joints = [float(math.degrees(a)) for a in left_rad]
        req.right_joints = [float(math.degrees(a)) for a in right_rad]
        left_str = '[' + ', '.join(f'{v:7.2f}' for v in req.left_joints) + ']'
        right_str = '[' + ', '.join(f'{v:7.2f}' for v in req.right_joints) + ']'
        self.get_logger().info(f"send_move L(deg)={left_str} R(deg)={right_str}")
        self._move_client.call_async(req)
        return True

    def execute_trajectory(self, goal_handle, arm_side):
        """以 10Hz 节奏下发轨迹点；未执行侧用 /joint_states 当前值填充."""
        self.get_logger().info(f"Executing {arm_side} arm trajectory (real)...")
        result = FollowJointTrajectory.Result()

        trajectory = goal_handle.request.trajectory
        joint_names = list(trajectory.joint_names)

        # 进入执行前刷新一次当前角度作为占位
        left_current, right_current = self._snapshot_current()

        # 准备本侧关节在 trajectory.joint_names 中的索引映射
        left_idx_map = {LEFT_JOINT_NAMES.index(n): i
                        for i, n in enumerate(joint_names) if n in LEFT_JOINT_NAMES}
        right_idx_map = {RIGHT_JOINT_NAMES.index(n): i
                         for i, n in enumerate(joint_names) if n in RIGHT_JOINT_NAMES}

        prev_time = 0.0
        next_send = time.monotonic()

        for point in trajectory.points:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.get_logger().info(f"{arm_side} arm goal canceled.")
                return result

            # 按 trajectory timing 等待到此 waypoint 的时刻
            current_time = point.time_from_start.sec + point.time_from_start.nanosec * 1e-9
            dt = current_time - prev_time
            if dt > 0:
                time.sleep(dt)
            prev_time = current_time

            # 按 arm_side 决定本帧左右臂的目标
            left_target = list(left_current)
            right_target = list(right_current)

            positions = list(point.positions)
            for j_idx, p_idx in left_idx_map.items():
                left_target[j_idx] = positions[p_idx]
            for j_idx, p_idx in right_idx_map.items():
                right_target[j_idx] = positions[p_idx]

            # 执行单臂时，未执行侧实时刷新为 /joint_states 最新值以防漂移
            if arm_side == "LEFT":
                _, right_target = self._snapshot_current()
                # 同时保留本帧 left_target 中我们规划的值
            elif arm_side == "RIGHT":
                left_target, _ = self._snapshot_current()

            # 10Hz 节流
            now = time.monotonic()
            if now < next_send:
                time.sleep(next_send - now)
            next_send = time.monotonic() + CONTROL_PERIOD

            self._send_move(left_target, right_target)

            # 更新本地缓存（轨迹规划后续 waypoint 的占位用）
            left_current, right_current = left_target, right_target

        goal_handle.succeed()
        self.get_logger().info(f"{arm_side} arm real trajectory complete.")
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

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
import math

try:
    from interface_pkg.msg import MotFeedback, Robotstatus
    HAS_INTERFACE_PKG = True
except ImportError:
    HAS_INTERFACE_PKG = False

# Map from partial joint names to internal state indices
LEFT_JOINT_MAP = {
    f'ARM-L-J{i}_Joint': i - 1 for i in range(1, 8)
}
RIGHT_JOINT_MAP = {
    f'ARM-R-J{i}_Joint': i - 1 for i in range(1, 8)
}


class JointStateBridge(Node):
    def __init__(self):
        super().__init__('joint_state_bridge')

        self.pub_joint_states = self.create_publisher(JointState, '/joint_states', 10)

        # Subscribe to sim joint commands (from sim_arm_controller) — always available
        self.sub_sim = self.create_subscription(
            JointState, '/sim_joint_commands', self.sim_joint_callback, 10)

        # Subscribe to hardware feedback — optional, requires interface_pkg
        if HAS_INTERFACE_PKG:
            self.sub_motor = self.create_subscription(
                MotFeedback, '/motor_feedback', self.motor_callback, 10)
            self.sub_status = self.create_subscription(
                Robotstatus, '/robot_status', self.status_callback, 10)

        self.sj_joint = 0.0
        self.tou_joint = 0.0
        self.tou2_joint = 0.0
        self.left_joints = [0.0] * 7
        self.right_joints = [0.0] * 7

        self.timer = self.create_timer(0.05, self.publish_joint_states)

        if HAS_INTERFACE_PKG:
            self.get_logger().info("T1 JointState bridge started (with hardware feedback).")
        else:
            self.get_logger().info("T1 JointState bridge started (sim-only, interface_pkg not available).")

    def motor_callback(self, msg):
        try:
            if hasattr(msg, 'pos'):
                self.sj_joint = msg.pos / 100000.0
            if hasattr(msg, 'head_back_angle'):
                self.tou2_joint = math.radians(msg.head_back_angle)
        except Exception as e:
            self.get_logger().error(f"Error parsing MotFeedback: {e}")

    def status_callback(self, msg):
        try:
            if len(msg.left_joint_positions) >= 7:
                self.left_joints = [math.radians(a) for a in msg.left_joint_positions[:7]]
            if len(msg.right_joint_positions) >= 7:
                self.right_joints = [math.radians(a) for a in msg.right_joint_positions[:7]]
            if hasattr(msg, 'head_back_angle'):
                self.tou2_joint = math.radians(msg.head_back_angle)
        except Exception as e:
            self.get_logger().error(f"Error parsing Robotstatus: {e}")

    def sim_joint_callback(self, msg: JointState):
        try:
            for i, name in enumerate(msg.name):
                pos = msg.position[i]
                if name in LEFT_JOINT_MAP:
                    self.left_joints[LEFT_JOINT_MAP[name]] = pos
                elif name in RIGHT_JOINT_MAP:
                    self.right_joints[RIGHT_JOINT_MAP[name]] = pos
                elif name == 'SJ_Joint':
                    # 若上游以 mm 发布则换算为 m；URDF prismatic 量程通常 < 2m
                    self.sj_joint = pos
                elif name == 'tou_Joint':
                    self.tou_joint = pos
                elif name == 'tou2_Joint':
                    self.tou2_joint = pos
        except Exception as e:
            self.get_logger().error(f"Error parsing sim joint commands: {e}")

    def publish_joint_states(self):
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()

        js.name = [
            'ZQ_steer_Joint', 'ZQ_drive_Joint',
            'RQ_steer_Joint', 'RQ_drive_Joint',
            'ZH_steer_Joint', 'ZH_drive_Joint',
            'RH_steer_Joint', 'ZH_drive_Joint1',
            'SJ_Joint',
            'ARM-R-J1_Joint', 'ARM-R-J2_Joint', 'ARM-R-J3_Joint', 'ARM-R-J4_Joint',
            'ARM-R-J5_Joint', 'ARM-R-J6_Joint', 'ARM-R-J7_Joint',
            'ARM-L-J1_Joint', 'ARM-L-J2_Joint', 'ARM-L-J3_Joint', 'ARM-L-J4_Joint',
            'ARM-L-J5_Joint', 'ARM-L-J6_Joint', 'ARM-L-J7_Joint',
            'tou_Joint', 'tou2_Joint'
        ]

        js.position = (
            [0.0] * 8 +
            [self.sj_joint] +
            self.right_joints + self.left_joints +
            [self.tou_joint, self.tou2_joint]
        )

        self.pub_joint_states.publish(js)


def main(args=None):
    rclpy.init(args=args)
    node = JointStateBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

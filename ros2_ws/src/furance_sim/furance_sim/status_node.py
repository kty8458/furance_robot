import json
import random

from rclpy.node import Node
from std_msgs.msg import String


class StatusNode(Node):
    def __init__(self):
        super().__init__('status_node')
        self.get_logger().info('StatusNode started')

        self._pub = self.create_publisher(String, '/robot_status', 10)

        # Mutable state
        self._position = {'x': 3.25, 'y': 1.78, 'theta': 0.52}
        self._battery = 85
        self._charging = False
        self._enabled = True
        self._lift_height = 0.0
        self._task_status = 'idle'
        self._gripper = {
            'left': {'state': 'open', 'force': 0.0},
            'right': {'state': 'open', 'force': 0.0},
        }
        self._arm = {
            'left': {'joint_angles': [0.0, -0.5, 0.3, 0.0, 0.2, 0.0, 0.0], 'status': 'idle'},
            'right': {'joint_angles': [0.0, 0.3, -0.2, 0.0, -0.1, 0.0, 0.0], 'status': 'idle'},
        }

        self._tick_count = 0

        # Publish every 2 seconds
        self._timer = self.create_timer(2.0, self._publish_status)

        # Log summary every 10 seconds (5 ticks)
        self._summary_timer = self.create_timer(10.0, self._log_summary)

    def _publish_status(self):
        self._tick_count += 1
        self._evolve_state()

        msg = String()
        msg.data = json.dumps({
            'position': self._position,
            'current_map': 'workshop_map',
            'lift_height': self._lift_height,
            'gripper': self._gripper,
            'battery': self._battery,
            'charging': self._charging,
            'enabled': self._enabled,
            'error_code': 0,
            'task_status': self._task_status,
            'arm': self._arm,
        })
        self._pub.publish(msg)

    def _evolve_state(self):
        # Position: slow random drift
        self._position['x'] += random.uniform(-0.02, 0.02)
        self._position['y'] += random.uniform(-0.02, 0.02)
        self._position['theta'] += random.uniform(-0.01, 0.01)

        # Battery: drain every 30s when not charging, charge when charging
        if self._tick_count % 15 == 0:
            if not self._charging:
                self._battery = max(0, self._battery - 1)
            else:
                self._battery = min(100, self._battery + 2)

        # Arm: subtle random micro-adjustments
        for side in ('left', 'right'):
            angles = self._arm[side]['joint_angles']
            self._arm[side]['joint_angles'] = [
                round(a + random.uniform(-0.01, 0.01), 3) for a in angles
            ]

        # Task status: rarely change
        if random.random() < 0.05:
            self._task_status = random.choice(['idle', 'moving', 'working'])
            self._arm['left']['status'] = 'working' if self._task_status == 'working' else 'idle'
            self._arm['right']['status'] = 'working' if self._task_status == 'working' else 'idle'

    def _log_summary(self):
        self.get_logger().info(
            f'Status: pos=({self._position["x"]:.2f},{self._position["y"]:.2f}), '
            f'bat={self._battery}%, charging={self._charging}, '
            f'enabled={self._enabled}, task={self._task_status}'
        )


def main(args=None):
    import rclpy
    rclpy.init(args=args)
    node = StatusNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

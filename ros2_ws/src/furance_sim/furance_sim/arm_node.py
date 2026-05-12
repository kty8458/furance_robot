import json
import random
import time

from rclpy.node import Node
from furance_interfaces.srv import GenericCommand

NUM_JOINTS = 7


class ArmNode(Node):
    def __init__(self):
        super().__init__('arm_node')
        self.get_logger().info('ArmNode started')

        self._joint_angles = {
            'left': [0.0] * NUM_JOINTS,
            'right': [0.0] * NUM_JOINTS,
        }

        self._move_srv = self.create_service(GenericCommand, '/ArmMoveCommand', self._handle_move)
        self._teach_srv = self.create_service(GenericCommand, '/ArmTeachExec', self._handle_teach)

    def _handle_move(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        arm = params.get('arm', 'left')
        target_angles = params.get('joint_angles', [0.0] * NUM_JOINTS)

        self.get_logger().info(f'ArmMoveCommand: moving {arm} arm to {target_angles}')

        delay = random.uniform(0.5, 2.0)
        self.get_logger().info(f'Arm motion started, estimated time {delay:.1f}s')
        time.sleep(delay)

        self._joint_angles[arm] = target_angles[:NUM_JOINTS]
        self.get_logger().info(f'Arm motion completed: {arm} arm at {self._joint_angles[arm]}')

        response.success = True
        response.message = f'{arm} arm moved'
        response.result_json = json.dumps({
            'arm': arm,
            'joint_angles': self._joint_angles[arm],
        })
        return response

    def _handle_teach(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        arm = params.get('arm', 'left')
        teach_name = params.get('name', 'unnamed')

        self.get_logger().info(f'ArmTeachExec: executing teach program "{teach_name}" on {arm} arm')

        delay = random.uniform(1.0, 3.0)
        self.get_logger().info(f'Teach execution started, estimated time {delay:.1f}s')
        time.sleep(delay)

        # Simulate some angle changes from teach
        self._joint_angles[arm] = [round(random.uniform(-1.5, 1.5), 2) for _ in range(NUM_JOINTS)]
        self.get_logger().info(f'Teach execution completed: {arm} arm at {self._joint_angles[arm]}')

        response.success = True
        response.message = f'Teach program "{teach_name}" executed'
        response.result_json = json.dumps({
            'arm': arm,
            'joint_angles': self._joint_angles[arm],
        })
        return response


def main(args=None):
    import rclpy
    rclpy.init(args=args)
    node = ArmNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

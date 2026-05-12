import json
import random
import time

from rclpy.node import Node
from furance_interfaces.srv import GenericCommand


class GripperNode(Node):
    def __init__(self):
        super().__init__('gripper_node')
        self.get_logger().info('GripperNode started')

        self._state = {
            'left': {'state': 'open', 'force': 0.0},
            'right': {'state': 'open', 'force': 0.0},
        }

        self._gripper_srv = self.create_service(GenericCommand, '/GripperCommand', self._handle_gripper)
        self._grab_srv = self.create_service(GenericCommand, '/GrabCommand', self._handle_grab)
        self._place_srv = self.create_service(GenericCommand, '/PlaceCommand', self._handle_place)

    def _handle_gripper(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        arm = params.get('arm', 'left')
        action = params.get('action', 'open')
        force = params.get('force', 50.0)

        self.get_logger().info(f'GripperCommand: {arm} gripper {action} with force {force}N')

        delay = random.uniform(0.3, 1.0)
        time.sleep(delay)

        self._state[arm] = {'state': 'closed' if action == 'close' else 'open', 'force': force if action == 'close' else 0.0}
        self.get_logger().info(f'Gripper {arm} now {self._state[arm]["state"]}')

        response.success = True
        response.message = f'{arm} gripper {action}'
        response.result_json = json.dumps(self._state[arm])
        return response

    def _handle_grab(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        target = params.get('target', 'unknown')
        arm = params.get('arm', 'left')

        self.get_logger().info(f'GrabCommand: grabbing {target} with {arm} arm')

        delay = random.uniform(0.5, 1.5)
        self.get_logger().info(f'Grab started, estimated time {delay:.1f}s')
        time.sleep(delay)

        self._state[arm] = {'state': 'closed', 'force': 50.0}
        self.get_logger().info(f'Grab completed: {arm} gripper closed on {target}')

        response.success = True
        response.message = f'Grabbed {target}'
        response.result_json = json.dumps({'arm': arm, 'target': target, 'gripper': self._state[arm]})
        return response

    def _handle_place(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        target = params.get('target', 'unknown')
        arm = params.get('arm', 'left')

        self.get_logger().info(f'PlaceCommand: placing at {target} with {arm} arm')

        delay = random.uniform(0.5, 1.5)
        self.get_logger().info(f'Place started, estimated time {delay:.1f}s')
        time.sleep(delay)

        self._state[arm] = {'state': 'open', 'force': 0.0}
        self.get_logger().info(f'Place completed: {arm} gripper opened at {target}')

        response.success = True
        response.message = f'Placed at {target}'
        response.result_json = json.dumps({'arm': arm, 'target': target, 'gripper': self._state[arm]})
        return response


def main(args=None):
    import rclpy
    rclpy.init(args=args)
    node = GripperNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

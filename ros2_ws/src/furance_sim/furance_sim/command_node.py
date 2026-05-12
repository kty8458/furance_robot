import json
import random
import time

from rclpy.node import Node
from furance_interfaces.srv import GenericCommand


class CommandNode(Node):
    def __init__(self):
        super().__init__('command_node')
        self.get_logger().info('CommandNode started')

        self._enabled = True
        self._charging = False
        self._lift_height = 0.0

        self._home_srv = self.create_service(GenericCommand, '/HomeCommand', self._handle_home)
        self._enable_srv = self.create_service(GenericCommand, '/EnableCommand', self._handle_enable)
        self._charge_srv = self.create_service(GenericCommand, '/ChargeCommand', self._handle_charge)
        self._lift_srv = self.create_service(GenericCommand, '/LiftCommand', self._handle_lift)

    def _handle_home(self, request, response):
        self.get_logger().info('HomeCommand: returning to home position')

        delay = random.uniform(1.0, 2.5)
        self.get_logger().info(f'Homing started, estimated time {delay:.1f}s')
        time.sleep(delay)

        self._lift_height = 0.0
        self.get_logger().info('Homing completed: robot at home position')

        response.success = True
        response.message = 'Home position reached'
        response.result_json = json.dumps({'position': {'x': 0.0, 'y': 0.0, 'theta': 0.0}})
        return response

    def _handle_enable(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        enable = params.get('enable', True)
        clear_error = params.get('clear_error', False)

        if clear_error:
            self.get_logger().info('EnableCommand: clearing error state')
            self._enabled = True
            self.get_logger().info('Error cleared, robot enabled')
        else:
            self._enabled = enable
            self.get_logger().info(f'EnableCommand: robot {"enabled" if enable else "disabled"}')

        response.success = True
        response.message = f'Robot {"enabled" if self._enabled else "disabled"}'
        response.result_json = json.dumps({'enabled': self._enabled, 'error_code': 0})
        return response

    def _handle_charge(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        action = params.get('action', 'start')

        if action == 'start':
            self._charging = True
            self.get_logger().info('ChargeCommand: charging started')
        else:
            self._charging = False
            self.get_logger().info('ChargeCommand: charging stopped')

        response.success = True
        response.message = f'Charging {action}ed'
        response.result_json = json.dumps({'charging': self._charging})
        return response

    def _handle_lift(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        direction = params.get('direction', 'up')
        height = params.get('height', 100.0)

        self.get_logger().info(f'LiftCommand: lifting {direction} to height {height}mm')

        delay = random.uniform(0.5, 1.5)
        self.get_logger().info(f'Lift started, estimated time {delay:.1f}s')
        time.sleep(delay)

        self._lift_height = height if direction == 'up' else 0.0
        self.get_logger().info(f'Lift completed: height now at {self._lift_height}mm')

        response.success = True
        response.message = f'Lift {direction} to {height}mm'
        response.result_json = json.dumps({'lift_height': self._lift_height})
        return response


def main(args=None):
    import rclpy
    rclpy.init(args=args)
    node = CommandNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

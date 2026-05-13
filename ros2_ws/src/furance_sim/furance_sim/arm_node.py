import json
import os
import random
import time
from pathlib import Path

from rclpy.node import Node
from furance_interfaces.srv import GenericCommand

NUM_JOINTS = 7

# Default: resolve teach_dir from FURANCE_ROBOT_ROOT env or guess from source layout
_FURANCE_ROOT = os.environ.get("FURANCE_ROBOT_ROOT")
if _FURANCE_ROOT:
    _DEFAULT_TEACH_DIR = str(Path(_FURANCE_ROOT) / "robot_control" / "backend" / "data" / "teach")
else:
    _DEFAULT_TEACH_DIR = ""


class ArmNode(Node):
    def __init__(self):
        super().__init__('arm_node')
        self.get_logger().info('ArmNode started')

        self._joint_angles = {
            'left': [0.0] * NUM_JOINTS,
            'right': [0.0] * NUM_JOINTS,
        }

        # Teach data directory — must be set via ROS2 param or FURANCE_ROBOT_ROOT env
        self.declare_parameter('teach_dir', _DEFAULT_TEACH_DIR)
        self._teach_dir = Path(self.get_parameter('teach_dir').value)
        if not self._teach_dir or not self._teach_dir.exists():
            self.get_logger().warning(
                f'Teach directory not configured or does not exist: {self._teach_dir}. '
                'Set FURANCE_ROBOT_ROOT env or teach_dir ROS2 param.'
            )

        self._move_srv = self.create_service(GenericCommand, '/ArmMoveCommand', self._handle_move)
        self._teach_srv = self.create_service(GenericCommand, '/ArmTeachExec', self._handle_teach)
        self._get_teach_srv = self.create_service(GenericCommand, '/GetTeachPoints', self._handle_get_teach)

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

    def _handle_get_teach(self, request, response):
        """Return stored teach presets for a given robot and optional arm filter."""
        params = json.loads(request.params_json) if request.params_json else {}
        robot_id = params.get('robot_id', 'robot_001')
        arm_filter = params.get('arm', None)

        robot_dir = self._teach_dir / robot_id
        file_path = robot_dir / "presets.json"
        presets = self._load_presets(file_path)

        result_list = []
        for v in presets.values():
            if arm_filter and v.get('arm') != arm_filter:
                continue
            result_list.append(v)

        self.get_logger().info(
            f'GetTeachPoints: returning {len(result_list)} presets for robot {robot_id}'
            + (f' arm={arm_filter}' if arm_filter else '')
        )

        response.success = True
        response.message = f'{len(result_list)} teach points found'
        response.result_json = json.dumps(result_list)
        return response

    def _load_presets(self, file_path: Path) -> dict:
        if not file_path.exists():
            return {}
        return json.loads(file_path.read_text())


def main(args=None):
    import rclpy
    rclpy.init(args=args)
    node = ArmNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

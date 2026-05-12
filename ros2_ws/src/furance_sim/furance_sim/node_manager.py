import json
import subprocess
import signal

from rclpy.node import Node
from furance_interfaces.srv import GenericCommand

NODE_REGISTRY = {
    'navigation_node': {'package': 'furance_sim', 'executable': 'navigation_node'},
    'arm_node': {'package': 'furance_sim', 'executable': 'arm_node'},
    'gripper_node': {'package': 'furance_sim', 'executable': 'gripper_node'},
    'status_node': {'package': 'furance_sim', 'executable': 'status_node'},
    'command_node': {'package': 'furance_sim', 'executable': 'command_node'},
}

SELF_MANAGED = True  # node_manager is always running if responding


class NodeManager(Node):
    def __init__(self):
        super().__init__('node_manager')
        self.get_logger().info('NodeManager started')

        self._processes: dict[str, subprocess.Popen] = {}

        self._list_srv = self.create_service(GenericCommand, '/GetNodeList', self._handle_list)
        self._start_srv = self.create_service(GenericCommand, '/NodeStart', self._handle_start)
        self._stop_srv = self.create_service(GenericCommand, '/NodeStop', self._handle_stop)
        self._status_srv = self.create_service(GenericCommand, '/NodeStatus', self._handle_status)

    def _handle_list(self, request, response):
        self.get_logger().info('GetNodeList: listing all nodes')
        nodes = []
        for name in NODE_REGISTRY:
            status = 'running' if name in self._processes and self._processes[name].poll() is None else 'stopped'
            nodes.append({'name': name, 'status': status})
        # node_manager itself is always running
        nodes.append({'name': 'node_manager', 'status': 'running'})

        response.success = True
        response.message = 'OK'
        response.result_json = json.dumps(nodes)
        return response

    def _handle_start(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        name = params.get('name', '')

        if name == 'node_manager':
            response.success = False
            response.message = 'node_manager cannot be restarted'
            response.result_json = '{}'
            return response

        if name not in NODE_REGISTRY:
            self.get_logger().warning(f'NodeStart: unknown node {name}')
            response.success = False
            response.message = f'Unknown node: {name}'
            response.result_json = '{}'
            return response

        if name in self._processes and self._processes[name].poll() is None:
            self.get_logger().warning(f'NodeStart: node {name} already running')
            response.success = False
            response.message = f'Node {name} already running'
            response.result_json = '{}'
            return response

        info = NODE_REGISTRY[name]
        cmd = ['ros2', 'run', info['package'], info['executable']]
        self.get_logger().info(f'NodeStart: starting {name} with {" ".join(cmd)}')

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self._processes[name] = proc
            self.get_logger().info(f'NodeStart: node {name} started (pid={proc.pid})')
            response.success = True
            response.message = f'Node {name} started'
            response.result_json = json.dumps({'name': name, 'pid': proc.pid})
        except Exception as e:
            self.get_logger().error(f'NodeStart: failed to start {name}: {e}')
            response.success = False
            response.message = f'Failed to start {name}: {e}'
            response.result_json = '{}'

        return response

    def _handle_stop(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        name = params.get('name', '')

        if name == 'node_manager':
            response.success = False
            response.message = 'node_manager cannot be stopped'
            response.result_json = '{}'
            return response

        if name not in NODE_REGISTRY:
            response.success = False
            response.message = f'Unknown node: {name}'
            response.result_json = '{}'
            return response

        if name not in self._processes or self._processes[name].poll() is not None:
            self.get_logger().warning(f'NodeStop: node {name} not running')
            response.success = False
            response.message = f'Node {name} not running'
            response.result_json = '{}'
            return response

        proc = self._processes[name]
        self.get_logger().info(f'NodeStop: stopping {name} (pid={proc.pid})')
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        del self._processes[name]
        self.get_logger().info(f'NodeStop: node {name} stopped')

        response.success = True
        response.message = f'Node {name} stopped'
        response.result_json = '{}'
        return response

    def _handle_status(self, request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        name = params.get('name', '')

        if name == 'node_manager':
            response.success = True
            response.message = 'OK'
            response.result_json = json.dumps({'name': 'node_manager', 'status': 'running'})
            return response

        if name not in NODE_REGISTRY:
            response.success = False
            response.message = f'Unknown node: {name}'
            response.result_json = '{}'
            return response

        is_running = name in self._processes and self._processes[name].poll() is None
        pid = self._processes[name].pid if name in self._processes else None

        self.get_logger().info(f'NodeStatus: {name} is {"running" if is_running else "stopped"}')
        response.success = True
        response.message = 'OK'
        response.result_json = json.dumps({'name': name, 'status': 'running' if is_running else 'stopped', 'pid': pid})
        return response

    def destroy_node(self):
        # Clean up all managed processes
        for name, proc in list(self._processes.items()):
            if proc.poll() is None:
                self.get_logger().info(f'Shutting down managed node: {name}')
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
        super().destroy_node()


def main(args=None):
    import rclpy
    rclpy.init(args=args)
    node = NodeManager()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

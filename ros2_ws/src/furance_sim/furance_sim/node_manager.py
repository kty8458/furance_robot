import json
import os
import subprocess
import signal
import threading
from datetime import datetime

from rclpy.node import Node
from furance_interfaces.srv import GenericCommand

# Node entries: type='node' uses `ros2 run`, type='launch' uses `ros2 launch`
NODE_REGISTRY = {
    'navigation_node': {'type': 'node', 'package': 'furance_sim', 'executable': 'navigation_node'},
    'arm_node': {'type': 'node', 'package': 'furance_sim', 'executable': 'arm_node'},
    'gripper_node': {'type': 'node', 'package': 'furance_sim', 'executable': 'gripper_node'},
    'status_node': {'type': 'node', 'package': 'furance_sim', 'executable': 'status_node'},
    'command_node': {'type': 'node', 'package': 'furance_sim', 'executable': 'command_node'},
    't1_moveit': {'type': 'launch', 'package': 't1_moveit_config', 'launch_file': 't1_moveit_headless.launch.py', 'args': {'use_sim': 'true'}},
}

SELF_MANAGED = True

LOG_BASE_DIR = os.path.join(os.path.expanduser('~'), '.ros', 'node_manager_logs')


class NodeManager(Node):
    def __init__(self):
        super().__init__('node_manager')
        self.get_logger().info('NodeManager started')

        self._processes: dict[str, subprocess.Popen] = {}
        self._log_threads: dict[str, threading.Thread] = {}
        self._log_files: dict[str, object] = {}

        # Create session directory: one folder per node_manager lifetime
        self._session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self._session_dir = os.path.join(LOG_BASE_DIR, self._session_id)
        os.makedirs(self._session_dir, exist_ok=True)

        # Write session marker
        with open(os.path.join(self._session_dir, '.session'), 'w') as f:
            f.write(f'started={self._session_id}\n')

        self._list_srv = self.create_service(GenericCommand, '/GetNodeList', self._handle_list)
        self._start_srv = self.create_service(GenericCommand, '/NodeStart', self._handle_start)
        self._stop_srv = self.create_service(GenericCommand, '/NodeStop', self._handle_stop)
        self._status_srv = self.create_service(GenericCommand, '/NodeStatus', self._handle_status)
        self._logs_srv = self.create_service(GenericCommand, '/GetNodeLogDir', self._handle_log_dir)

    def _build_cmd(self, name: str, info: dict) -> list[str]:
        if info['type'] == 'launch':
            cmd = ['stdbuf', '-oL', 'ros2', 'launch', info['package'], info['launch_file']]
            for k, v in info.get('args', {}).items():
                cmd.append(f'{k}:={v}')
            return cmd
        else:
            return ['ros2', 'run', info['package'], info['executable']]

    def _log_reader(self, name: str, proc: subprocess.Popen):
        """Read stdout from subprocess and write to log file."""
        log_file = self._log_files.get(name)
        try:
            for raw_line in iter(proc.stdout.readline, b''):
                if not raw_line:
                    continue
                line = raw_line.decode('utf-8', errors='replace').rstrip('\n\r')
                if log_file:
                    try:
                        log_file.write(line + '\n')
                        log_file.flush()
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            if log_file:
                try:
                    log_file.close()
                except Exception:
                    pass
            self._log_files.pop(name, None)

    def _handle_list(self, request, response):
        self.get_logger().info('GetNodeList: listing all nodes')
        nodes = []
        for name, info in NODE_REGISTRY.items():
            status = 'running' if name in self._processes and self._processes[name].poll() is None else 'stopped'
            nodes.append({'name': name, 'status': status, 'type': info['type']})
        nodes.append({'name': 'node_manager', 'status': 'running', 'type': 'node'})

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
        cmd = self._build_cmd(name, info)
        self.get_logger().info(f'NodeStart: starting {name} with {" ".join(cmd)}')

        try:
            is_launch = info['type'] == 'launch'
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            env['RCUTILS_LOGGING_BUFFERED_STREAM'] = '1'
            env['RCUTILS_LOGGING_USE_STDOUT'] = '1'

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid if is_launch else None,
                env=env,
            )
            self._processes[name] = proc

            # Open log file in append mode
            log_path = os.path.join(self._session_dir, f'{name}.log')
            log_file = open(log_path, 'a')
            log_file.write(f'\n--- Started {name} at {datetime.now().isoformat()} (pid={proc.pid}) ---\n')
            log_file.flush()
            self._log_files[name] = log_file

            # Start background thread to read stdout and write to log file
            t = threading.Thread(target=self._log_reader, args=(name, proc), daemon=True)
            self._log_threads[name] = t
            t.start()

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
        info = NODE_REGISTRY[name]
        is_launch = info['type'] == 'launch'
        self.get_logger().info(f'NodeStop: stopping {name} (pid={proc.pid})')

        # Write stop marker
        log_file = self._log_files.get(name)
        if log_file:
            try:
                log_file.write(f'--- Stopped {name} at {datetime.now().isoformat()} ---\n')
                log_file.flush()
                log_file.close()
            except Exception:
                pass
            self._log_files.pop(name, None)

        if is_launch:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            except ProcessLookupError:
                pass
        else:
            proc.send_signal(signal.SIGINT)

        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if is_launch:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            proc.wait()

        del self._processes[name]
        self._log_threads.pop(name, None)
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

    def _handle_log_dir(self, request, response):
        """Return current session log directory path so backend can read files directly."""
        response.success = True
        response.message = 'OK'
        response.result_json = json.dumps({
            'session_id': self._session_id,
            'log_dir': self._session_dir,
        })
        return response

    def destroy_node(self):
        for name, proc in list(self._processes.items()):
            if proc.poll() is None:
                self.get_logger().info(f'Shutting down managed node: {name}')
                log_file = self._log_files.get(name)
                if log_file:
                    try:
                        log_file.write(f'--- Stopped {name} at {datetime.now().isoformat()} (shutdown) ---\n')
                        log_file.close()
                    except Exception:
                        pass
                info = NODE_REGISTRY.get(name, {})
                is_launch = info.get('type') == 'launch'
                if is_launch:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGINT)
                    except ProcessLookupError:
                        pass
                else:
                    proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if is_launch:
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    else:
                        proc.kill()
        self._log_files.clear()
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

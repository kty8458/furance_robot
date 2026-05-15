import asyncio
import logging
import os
import signal

from furance_shared.protocol.http_schema import ApiResponse
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient

logger = logging.getLogger(__name__)

# Launch file definitions: name -> config
LAUNCH_FILES = {
    "t1_moveit": {
        "package": "t1_moveit_config",
        "launch_file": "t1_moveit_headless.launch.py",
        "default_args": {"use_sim": "true"},
        "description": "T1 MoveIt (headless)",
    },
}

# Sample nodes for mock/development mode
MOCK_NODES = [
    {"name": "arm_controller", "status": "stopped"},
    {"name": "gripper_controller", "status": "stopped"},
    {"name": "navigation_node", "status": "stopped"},
    {"name": "status_publisher", "status": "stopped"},
]


def _check_result(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
    return ApiResponse(data=result)


class LaunchProcessManager:
    """Manages launch file subprocesses."""

    def __init__(self):
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def start_launch(self, name: str) -> bool:
        if name in self._processes and self._processes[name].returncode is None:
            logger.warning("Launch %s is already running", name)
            return True

        config = LAUNCH_FILES.get(name)
        if not config:
            logger.error("Unknown launch: %s", name)
            return False

        cmd = [
            "ros2", "launch",
            config["package"],
            config["launch_file"],
        ]
        for k, v in config.get("default_args", {}).items():
            cmd.append(f"{k}:={v}")

        try:
            env = os.environ.copy()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._processes[name] = proc
            logger.info("Started launch %s (pid=%d)", name, proc.pid)
            return True
        except Exception:
            logger.exception("Failed to start launch %s", name)
            return False

    async def stop_launch(self, name: str) -> bool:
        proc = self._processes.get(name)
        if proc is None or proc.returncode is not None:
            logger.warning("Launch %s is not running", name)
            return True

        try:
            proc.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(proc.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            del self._processes[name]
            logger.info("Stopped launch %s", name)
            return True
        except Exception:
            logger.exception("Failed to stop launch %s", name)
            return False

    def is_running(self, name: str) -> bool:
        proc = self._processes.get(name)
        return proc is not None and proc.returncode is None

    def list_launches(self) -> list[dict]:
        result = []
        for name, config in LAUNCH_FILES.items():
            result.append({
                "name": name,
                "description": config["description"],
                "package": config["package"],
                "status": "running" if self.is_running(name) else "stopped",
            })
        return result


class Ros2Manager:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None,
                 launch_manager: LaunchProcessManager | None = None):
        self._ros2 = ros2_client or MockRos2ServiceClient()
        self._is_mock = isinstance(self._ros2, MockRos2ServiceClient)
        self._launch_manager = launch_manager or LaunchProcessManager()

    async def list_nodes(self) -> ApiResponse:
        if self._is_mock:
            return ApiResponse(data=MOCK_NODES)
        result = await self._ros2.call_service("/GetNodeList", {})
        return _check_result(result)

    async def start_node(self, node_name: str) -> ApiResponse:
        if self._is_mock:
            return ApiResponse(data={"name": node_name, "status": "running"})
        result = await self._ros2.call_service("/NodeStart", {"name": node_name})
        return _check_result(result)

    async def stop_node(self, node_name: str) -> ApiResponse:
        if self._is_mock:
            return ApiResponse(data={"name": node_name, "status": "stopped"})
        result = await self._ros2.call_service("/NodeStop", {"name": node_name})
        return _check_result(result)

    async def node_status(self, node_name: str) -> ApiResponse:
        if self._is_mock:
            return ApiResponse(data={"name": node_name, "status": "stopped"})
        result = await self._ros2.call_service("/NodeStatus", {"name": node_name})
        return _check_result(result)

    async def list_launches(self) -> ApiResponse:
        return ApiResponse(data=self._launch_manager.list_launches())

    async def start_launch(self, name: str) -> ApiResponse:
        success = await self._launch_manager.start_launch(name)
        if not success:
            return ApiResponse(code=2001, message=f"Failed to start launch: {name}")
        return ApiResponse(data={"name": name, "status": "running"})

    async def stop_launch(self, name: str) -> ApiResponse:
        success = await self._launch_manager.stop_launch(name)
        if not success:
            return ApiResponse(code=2001, message=f"Failed to stop launch: {name}")
        return ApiResponse(data={"name": name, "status": "stopped"})

    async def launch_status(self, name: str) -> ApiResponse:
        return ApiResponse(data={
            "name": name,
            "status": "running" if self._launch_manager.is_running(name) else "stopped",
        })

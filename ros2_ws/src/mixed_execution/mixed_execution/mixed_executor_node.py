"""混合执行服务节点。

暴露服务 (GenericCommand):
  /mixed/list     -> 所有已登记混合功能的元数据 (名称/描述/参数schema/moves_base)
  /mixed/execute  -> params {function, params} -> {execution_id} (立即返回, 异步执行)
  /mixed/status   -> params {execution_id} -> {state, progress, message, result}
  /mixed/cancel   -> params {execution_id} -> 取消执行

执行线程内可通过 ctx:
  ctx.chassis                 底盘 HTTP 客户端 (move_with_params/rotate/...)
  ctx.ros_call(srv, params)   调用其他 GenericCommand 服务 (如 /camera/compute_pose)

配置: config/mixed_config.yaml (share 目录), 环境变量 MIXED_CONFIG_PATH 可覆盖路径。
"""

import json
import logging
import os
import threading
import time

import rclpy
from rclpy.node import Node

from furance_interfaces.srv import GenericCommand

from . import registry
from .chassis_http import ChassisHttpClient
from .executor import MixedExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mixed_execution.node")

SERVICE_TIMEOUT = 30.0


def _load_config() -> dict:
    """加载 mixed_config.yaml (env > share 目录)。"""
    import yaml
    paths = []
    env_path = os.environ.get("MIXED_CONFIG_PATH")
    if env_path:
        paths.append(env_path)
    try:
        from ament_index_python.packages import get_package_share_directory
        paths.append(os.path.join(
            get_package_share_directory("mixed_execution"),
            "config", "mixed_config.yaml"))
    except Exception:
        pass
    for p in paths:
        if p and os.path.exists(p):
            with open(p) as f:
                cfg = yaml.safe_load(f) or {}
            logger.info("Loaded mixed config from %s", p)
            return cfg
    logger.warning("mixed_config.yaml not found, using defaults")
    return {}


class RosCaller:
    """从工作线程调用 GenericCommand 服务的辅助类。

    主线程 rclpy.spin 处理回调, 工作线程 call_async 后轮询 future。
    """

    def __init__(self, node: Node):
        self._node = node
        self._clients: dict[str, object] = {}
        self._lock = threading.Lock()

    def call(self, service_name: str, params: dict, timeout: float = SERVICE_TIMEOUT) -> dict:
        """调用 GenericCommand 服务, 返回 {success, message, data}。"""
        with self._lock:
            client = self._clients.get(service_name)
            if client is None:
                client = self._node.create_client(GenericCommand, service_name)
                self._clients[service_name] = client
        if not client.wait_for_service(timeout_sec=2.0):
            return {"success": False, "message": f"Service not available: {service_name}"}
        req = GenericCommand.Request()
        req.command = service_name.lstrip("/")
        req.params_json = json.dumps(params or {})
        future = client.call_async(req)
        deadline = time.time() + timeout
        while not future.done() and time.time() < deadline:
            time.sleep(0.02)
        if not future.done():
            return {"success": False, "message": f"Service call timeout: {service_name}"}
        try:
            resp = future.result()
        except Exception as e:
            return {"success": False, "message": f"Service call failed: {e}"}
        data = {}
        if resp.result_json:
            try:
                data = json.loads(resp.result_json)
            except Exception:
                data = {}
        return {"success": bool(resp.success), "message": resp.message, "data": data}


def main(args=None):
    rclpy.init(args=args)
    node = Node("mixed_executor")
    logger.info("MixedExecutor node starting...")

    cfg = _load_config()
    chassis = ChassisHttpClient.from_config(cfg.get("chassis"))
    ros_caller = RosCaller(node)
    executor = MixedExecutor(chassis=chassis, ros_caller=ros_caller.call)

    # ---- /mixed/list ----
    def _handle_list(request, response):
        try:
            funcs = registry.list_functions()
            response.success = True
            response.message = f"{len(funcs)} functions"
            response.result_json = json.dumps(funcs)
        except Exception as e:
            logger.exception("list failed")
            response.success = False
            response.message = str(e)
        return response

    # ---- /mixed/execute ----
    def _handle_execute(request, response):
        try:
            params = json.loads(request.params_json) if request.params_json else {}
            function = params.get("function", "")
            fn_params = params.get("params") or {}
            if not function:
                response.success = False
                response.message = "Param 'function' required"
                return response
            result = executor.start(function, fn_params)
            response.success = result["success"]
            response.message = result.get("message", "")
            if result.get("success"):
                response.result_json = json.dumps(
                    {"execution_id": result["execution_id"]})
        except Exception as e:
            logger.exception("execute failed")
            response.success = False
            response.message = str(e)
        return response

    # ---- /mixed/status ----
    def _handle_status(request, response):
        try:
            params = json.loads(request.params_json) if request.params_json else {}
            execution_id = params.get("execution_id", "")
            if not execution_id:
                response.success = False
                response.message = "Param 'execution_id' required"
                return response
            state = executor.status(execution_id)
            response.success = state.get("state") != "unknown"
            response.message = state.get("state", "unknown")
            response.result_json = json.dumps(state)
        except Exception as e:
            logger.exception("status failed")
            response.success = False
            response.message = str(e)
        return response

    # ---- /mixed/cancel ----
    def _handle_cancel(request, response):
        try:
            params = json.loads(request.params_json) if request.params_json else {}
            execution_id = params.get("execution_id", "")
            if not execution_id:
                response.success = False
                response.message = "Param 'execution_id' required"
                return response
            result = executor.cancel(execution_id)
            response.success = result["success"]
            response.message = result.get("message", "")
        except Exception as e:
            logger.exception("cancel failed")
            response.success = False
            response.message = str(e)
        return response

    node.create_service(GenericCommand, "/mixed/list", _handle_list)
    node.create_service(GenericCommand, "/mixed/execute", _handle_execute)
    node.create_service(GenericCommand, "/mixed/status", _handle_status)
    node.create_service(GenericCommand, "/mixed/cancel", _handle_cancel)
    logger.info("MixedExecutor ready: /mixed/list|execute|status|cancel, functions=%s",
                [f["name"] for f in registry.list_functions()])

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

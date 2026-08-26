"""混合功能执行器: 线程池执行 + 状态跟踪 + 取消。

执行模式:
  /mixed/execute 立即返回 execution_id, 脚本在工作线程中执行;
  /mixed/status 轮询状态 (running/succeeded/failed/cancelled + progress);
  /mixed/cancel 设置取消标志, 脚本通过 ctx.check_cancel() 响应。
"""

import logging
import threading
import time
import uuid
from typing import Any, Callable, Optional

from . import registry
from .chassis_http import ChassisHttpClient

logger = logging.getLogger("mixed_execution.executor")


class MixedCancelled(Exception):
    """脚本被取消。"""


class ExecutionContext:
    """传给混合功能函数的上下文对象。

    函数签名: fn(ctx, **params), 其中:
      ctx.set_progress(pct, message)  上报进度 (0-100)
      ctx.check_cancel()              检查取消 (被取消时抛 MixedCancelled)
      ctx.chassis                     底盘 HTTP 客户端 (可选)
      ctx.ros_call(service, params)   调用 ROS2 GenericCommand 服务 (可选)
    """

    def __init__(self, execution_id: str, params: dict,
                 cancel_event: threading.Event,
                 chassis: Optional[ChassisHttpClient] = None,
                 ros_call: Optional[Callable] = None):
        self.execution_id = execution_id
        self.params = params
        self._cancel_event = cancel_event
        self._progress = 0
        self._message = ""
        self.chassis = chassis
        self.ros_call = ros_call

    def set_progress(self, pct: float, message: str = "") -> None:
        self._progress = max(0.0, min(100.0, float(pct)))
        if message:
            self._message = message
        logger.info("mixed[%s] progress=%.0f%% %s", self.execution_id, self._progress, message)

    def check_cancel(self) -> None:
        if self._cancel_event.is_set():
            raise MixedCancelled("Cancelled by user")

    def sleep(self, seconds: float) -> None:
        """可中断的 sleep (0.1s 粒度检查取消)。"""
        end = time.time() + seconds
        while time.time() < end:
            self.check_cancel()
            time.sleep(min(0.1, max(0.0, end - time.time())))
        self.check_cancel()

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def message(self) -> str:
        return self._message


class MixedExecutor:
    """管理混合功能执行实例。"""

    def __init__(self, chassis: Optional[ChassisHttpClient] = None,
                 ros_call: Optional[Callable] = None,
                 max_finished: int = 50):
        self._chassis = chassis
        self._ros_call = ros_call
        self._executions: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max_finished = max_finished

    def start(self, function_name: str, params: Optional[dict] = None) -> dict:
        """启动一个混合功能执行, 返回 {success, message, execution_id?}。"""
        func = registry.get_function(function_name)
        if func is None:
            return {"success": False, "message": f"Unknown mixed function: {function_name}"}

        params = dict(params or {})
        # 用 schema 默认值补齐缺失参数
        for p in func.params_schema:
            if p["name"] not in params or params[p["name"]] is None:
                params[p["name"]] = p.get("default")

        execution_id = uuid.uuid4().hex[:12]
        cancel_event = threading.Event()
        ctx = ExecutionContext(execution_id, params, cancel_event,
                               chassis=self._chassis, ros_call=self._ros_call)
        state = {
            "execution_id": execution_id,
            "function": function_name,
            "state": "running",
            "progress": 0.0,
            "message": "",
            "result": None,
            "error": None,
            "started_at": time.time(),
            "cancel_event": cancel_event,
            "ctx": ctx,
        }
        with self._lock:
            self._executions[execution_id] = state
            self._prune_finished()

        thread = threading.Thread(
            target=self._run, args=(state, func, ctx), daemon=True,
            name=f"mixed-{function_name}-{execution_id}")
        thread.start()
        logger.info("Started mixed function '%s' execution_id=%s params=%s",
                    function_name, execution_id, params)
        return {"success": True, "message": "Started",
                "execution_id": execution_id}

    def _run(self, state: dict, func: registry.MixedFunction,
             ctx: ExecutionContext) -> None:
        try:
            result = func.fn(ctx, **ctx.params)
            state["state"] = "succeeded"
            state["result"] = result
            state["progress"] = 100.0
            state["message"] = "Done"
            logger.info("Mixed function '%s' (%s) succeeded", func.name, state["execution_id"])
        except MixedCancelled:
            state["state"] = "cancelled"
            state["message"] = "Cancelled"
            logger.info("Mixed function '%s' (%s) cancelled", func.name, state["execution_id"])
        except Exception as e:
            state["state"] = "failed"
            state["error"] = str(e)
            state["message"] = f"Failed: {e}"
            logger.exception("Mixed function '%s' (%s) failed", func.name, state["execution_id"])

    def status(self, execution_id: str) -> dict:
        """返回执行状态; 不存在时 state='unknown'。"""
        with self._lock:
            state = self._executions.get(execution_id)
            if state is None:
                return {"execution_id": execution_id, "state": "unknown"}
            return self._public_state(state)

    def cancel(self, execution_id: str) -> dict:
        with self._lock:
            state = self._executions.get(execution_id)
            if state is None:
                return {"success": False, "message": f"Unknown execution: {execution_id}"}
            if state["state"] != "running":
                return {"success": False,
                        "message": f"Execution not running (state={state['state']})"}
            state["cancel_event"].set()
        # 同时取消底盘移动 (如脚本正在 move_with_params 阻塞)
        if self._chassis is not None:
            try:
                self._chassis.cancel_move_with_params()
            except Exception:
                logger.exception("Cancel chassis move failed for %s", execution_id)
        return {"success": True, "message": "Cancel requested"}

    @staticmethod
    def _public_state(state: dict) -> dict:
        ctx = state.get("ctx")
        return {
            "execution_id": state["execution_id"],
            "function": state["function"],
            "state": state["state"],
            "progress": ctx.progress if state["state"] == "running" else state["progress"],
            "message": ctx.message if state["state"] == "running" else state["message"],
            "result": state["result"],
            "error": state["error"],
        }

    def _prune_finished(self) -> None:
        """保留最近 N 条已结束的执行记录 (锁内调用)。"""
        finished = [(k, v) for k, v in self._executions.items() if v["state"] != "running"]
        if len(finished) > self._max_finished:
            for k, _ in finished[:-self._max_finished]:
                del self._executions[k]

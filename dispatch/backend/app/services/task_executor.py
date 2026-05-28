import asyncio
import json
import logging
import time
from app.core.database import Database
from app.models.task import TaskStepType, DelayStepConfig

logger = logging.getLogger(__name__)


class TaskExecutor:
    def __init__(self, db: Database, robot_proxy, sampler_service, ws_manager=None):
        self._db = db
        self._robot_proxy = robot_proxy
        self._sampler = sampler_service
        self._ws_manager = ws_manager
        self._active_executions: dict[int, asyncio.Event] = {}
        self._critical_alarm_received = asyncio.Event()

    def notify_critical_alarm(self):
        self._critical_alarm_received.set()

    async def execute(self, template_id: str, trigger_type: str = "manual") -> dict:
        template = await self._db.fetch_one("SELECT * FROM task_templates WHERE id = ?", (template_id,))
        if not template:
            return {"status": "error", "error_msg": f"Template {template_id} not found"}

        steps = json.loads(template["steps_json"])
        now = time.time()

        await self._db.execute(
            "INSERT INTO task_executions (task_template_id, trigger_type, status, started_at) VALUES (?, ?, ?, ?)",
            (template_id, trigger_type, "running", now),
        )
        execution = await self._db.fetch_one(
            "SELECT * FROM task_executions WHERE task_template_id = ? ORDER BY id DESC LIMIT 1",
            (template_id,),
        )
        execution_id = execution["id"]
        cancel_event = asyncio.Event()
        self._active_executions[execution_id] = cancel_event
        self._critical_alarm_received.clear()

        try:
            for i, step in enumerate(steps):
                if cancel_event.is_set():
                    await self._update_execution(execution_id, "cancelled", error_msg="Cancelled by user")
                    return {"status": "cancelled", "execution_id": execution_id}

                if self._critical_alarm_received.is_set():
                    await self._update_execution(execution_id, "failed", error_msg="Critical alarm triggered")
                    return {"status": "failed", "execution_id": execution_id}

                step_now = time.time()
                await self._db.execute(
                    "INSERT INTO execution_step_logs (execution_id, step_order, step_id, step_type, step_config_json, status, started_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (execution_id, i + 1, step["id"], step["type"], json.dumps(step.get("config", {})), "running", step_now),
                )

                step_log = await self._db.fetch_one(
                    "SELECT id FROM execution_step_logs WHERE execution_id = ? AND step_order = ?",
                    (execution_id, i + 1),
                )
                step_log_id = step_log["id"]

                try:
                    if step["type"] == TaskStepType.WORKFLOW:
                        await self._execute_workflow_step(step, execution_id, step_log_id, cancel_event)
                    elif step["type"] == TaskStepType.SAMPLER:
                        await self._execute_sampler_step(step, execution_id, step_log_id, cancel_event)
                    elif step["type"] == TaskStepType.DELAY:
                        await self._execute_delay_step(step, execution_id, step_log_id, cancel_event)
                except Exception as e:
                    logger.exception("Step %s failed", step.get("label", step["id"]))
                    await self._db.execute(
                        "UPDATE execution_step_logs SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
                        ("failed", time.time(), str(e), step_log_id),
                    )
                    await self._update_execution(execution_id, "failed", error_msg=f"Step '{step.get('label', step['id'])}' failed: {e}")
                    return {"status": "failed", "execution_id": execution_id}

                await self._db.execute(
                    "UPDATE execution_step_logs SET status = ?, completed_at = ? WHERE id = ?",
                    ("completed", time.time(), step_log_id),
                )

            await self._update_execution(execution_id, "completed")
            return {"status": "completed", "execution_id": execution_id}
        finally:
            self._active_executions.pop(execution_id, None)

    async def _execute_workflow_step(self, step, execution_id, step_log_id, cancel_event):
        config = step.get("config", {})
        robot_id = config.get("robot_id", "robot_001")
        workflow_name = config.get("workflow_name", "")

        resp = await self._robot_proxy.forward(
            robot_id,
            f"/api/v1/robot/{robot_id}/workflows/{workflow_name}/execute",
            {"nav_params": []},
        )
        if resp.code != 0:
            raise Exception(f"Failed to start workflow: {resp.message}")

        wf_execution_id = resp.data.get("execution_id", "")
        sub_results = []

        while True:
            if cancel_event.is_set():
                await self._robot_proxy.forward(
                    robot_id,
                    f"/api/v1/robot/{robot_id}/workflows/{workflow_name}/cancel",
                )
                raise Exception("Workflow cancelled")

            status_resp = await self._robot_proxy.forward_get(
                robot_id,
                f"/api/v1/robot/{robot_id}/workflows/executions/{wf_execution_id}",
            )
            if status_resp.code != 0:
                break

            await asyncio.sleep(1.0)

        await self._db.execute(
            "UPDATE execution_step_logs SET sub_step_results_json = ? WHERE id = ?",
            (json.dumps(sub_results), step_log_id),
        )

    async def _execute_sampler_step(self, step, execution_id, step_log_id, cancel_event):
        config = step.get("config", {})
        command = config.get("command", "")

        if command == "start":
            resp = await self._sampler.start()
        elif command == "stop":
            resp = await self._sampler.stop()
        else:
            raise Exception(f"Unknown sampler command: {command}")

        if resp.code != 0:
            raise Exception(f"Sampler command failed: {resp.message}")

    async def _execute_delay_step(self, step, execution_id, step_log_id, cancel_event):
        config = DelayStepConfig(**step.get("config", {}))
        for _ in range(int(config.seconds)):
            if cancel_event.is_set():
                raise Exception("Delay cancelled")
            await asyncio.sleep(1.0)

    async def _update_execution(self, execution_id, status, error_msg=None):
        now = time.time()
        if error_msg:
            await self._db.execute(
                "UPDATE task_executions SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
                (status, now, error_msg, execution_id),
            )
        else:
            await self._db.execute(
                "UPDATE task_executions SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, execution_id),
            )

    async def cancel(self, execution_id: int) -> bool:
        event = self._active_executions.get(execution_id)
        if event is None:
            return False
        event.set()
        return True

    async def list_executions(self, limit: int = 50) -> list[dict]:
        return await self._db.fetch_all(
            "SELECT * FROM task_executions ORDER BY id DESC LIMIT ?", (limit,)
        )

    async def get_execution(self, execution_id: int) -> dict | None:
        execution = await self._db.fetch_one(
            "SELECT * FROM task_executions WHERE id = ?", (execution_id,)
        )
        if not execution:
            return None
        steps = await self._db.fetch_all(
            "SELECT * FROM execution_step_logs WHERE execution_id = ? ORDER BY step_order",
            (execution_id,),
        )
        execution["steps"] = steps
        return execution

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
        # active executions: id -> cancel event (covers both queued and running)
        self._active_executions: dict[int, asyncio.Event] = {}
        # ordered queue of (execution_id, template_id)
        self._queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._current_execution_id: int | None = None
        self._critical_alarm_received = asyncio.Event()

    def notify_critical_alarm(self):
        self._critical_alarm_received.set()

    def _ensure_worker(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def _worker_loop(self):
        """Single-consumer worker: pulls queued executions in FIFO order."""
        while True:
            execution_id, template_id = await self._queue.get()
            cancel_event = self._active_executions.get(execution_id)
            if cancel_event is None:
                self._queue.task_done()
                continue

            if cancel_event.is_set():
                # Cancelled while queued
                await self._update_execution(execution_id, "cancelled", error_msg="Cancelled while queued")
                self._active_executions.pop(execution_id, None)
                self._queue.task_done()
                continue

            # Transition pending -> running
            now = time.time()
            await self._db.execute(
                "UPDATE task_executions SET status = ?, started_at = ? WHERE id = ?",
                ("running", now, execution_id),
            )
            self._current_execution_id = execution_id
            try:
                await self._run(execution_id, template_id, cancel_event)
            finally:
                self._current_execution_id = None
                self._active_executions.pop(execution_id, None)
                self._queue.task_done()

    async def start_execution(self, template_id: str, trigger_type: str = "manual") -> int | None:
        """Enqueue a task. If the worker is idle, it runs immediately; otherwise it waits in queue."""
        template = await self._db.fetch_one("SELECT id FROM task_templates WHERE id = ?", (template_id,))
        if not template:
            return None

        now = time.time()
        idle = self._current_execution_id is None and self._queue.empty()
        initial_status = "running" if idle else "pending"
        await self._db.execute(
            "INSERT INTO task_executions (task_template_id, trigger_type, status, started_at) VALUES (?, ?, ?, ?)",
            (template_id, trigger_type, initial_status, now),
        )
        row = await self._db.fetch_one(
            "SELECT id FROM task_executions WHERE task_template_id = ? ORDER BY id DESC LIMIT 1",
            (template_id,),
        )
        execution_id = row["id"]
        cancel_event = asyncio.Event()
        self._active_executions[execution_id] = cancel_event

        await self._queue.put((execution_id, template_id))
        self._ensure_worker()
        return execution_id

    def queue_snapshot(self) -> dict:
        """Return a snapshot of the current queue state."""
        pending_ids = [eid for eid, _ in list(self._queue._queue)]  # type: ignore[attr-defined]
        return {
            "current_execution_id": self._current_execution_id,
            "pending_execution_ids": pending_ids,
            "queue_length": len(pending_ids),
        }

    async def _run(self, execution_id: int, template_id: str, cancel_event: asyncio.Event):
        """Background task body. Reads template, executes steps, updates DB."""
        try:
            template = await self._db.fetch_one("SELECT * FROM task_templates WHERE id = ?", (template_id,))
            steps = json.loads(template["steps_json"])
            self._critical_alarm_received.clear()

            for i, step in enumerate(steps):
                if cancel_event.is_set():
                    await self._update_execution(execution_id, "cancelled", error_msg="Cancelled by user")
                    return
                if self._critical_alarm_received.is_set():
                    await self._update_execution(execution_id, "failed", error_msg="Critical alarm triggered")
                    return

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
                    return

                await self._db.execute(
                    "UPDATE execution_step_logs SET status = ?, completed_at = ? WHERE id = ?",
                    ("completed", time.time(), step_log_id),
                )

            await self._update_execution(execution_id, "completed")
        except Exception as e:
            logger.exception("Task execution %s crashed", execution_id)
            await self._update_execution(execution_id, "failed", error_msg=str(e))

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
        sub_results: list[dict] = []
        last_index = -1
        final_status = None
        final_error = None

        async def _persist():
            await self._db.execute(
                "UPDATE execution_step_logs SET sub_step_results_json = ? WHERE id = ?",
                (json.dumps(sub_results), step_log_id),
            )

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
                raise Exception(f"Failed to poll workflow status: {status_resp.message}")

            data = status_resp.data or {}
            idx = data.get("current_step_index", 0)
            now = time.time()

            if idx and idx != last_index:
                # Complete the previous sub-step (if any)
                if sub_results:
                    prev = sub_results[-1]
                    if prev["status"] == "running":
                        prev["status"] = "completed"
                        prev["completed_at"] = now
                # Append the new sub-step as running
                sub_results.append({
                    "step_index": idx,
                    "step_id": data.get("current_step_id"),
                    "label": data.get("current_step_label"),
                    "status": "running",
                    "started_at": now,
                    "completed_at": None,
                })
                last_index = idx
                await _persist()

            if not data.get("active", True):
                final_status = data.get("status")
                final_error = data.get("error_msg")
                if sub_results:
                    last = sub_results[-1]
                    if last["status"] == "running":
                        last["status"] = "failed" if final_status in ("failed", "cancelled") else "completed"
                        last["completed_at"] = now
                        if final_error and last["status"] == "failed":
                            last["error_msg"] = final_error
                await _persist()
                break

            await asyncio.sleep(1.0)

        if final_status == "failed":
            raise Exception(final_error or "Workflow failed")
        if final_status == "cancelled":
            raise Exception("Workflow cancelled by robot")

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
        if event is not None:
            event.set()
            # If it's still pending (queued, not yet running), update DB immediately.
            # The worker will see the cancel event when it dequeues, but the UI should
            # reflect cancellation right away.
            row = await self._db.fetch_one(
                "SELECT status FROM task_executions WHERE id = ?", (execution_id,)
            )
            if row and row["status"] == "pending":
                await self._db.execute(
                    "UPDATE task_executions SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
                    ("cancelled", time.time(), "Cancelled while queued", execution_id),
                )
            return True
        # Orphan: no live task. If it's still marked running/pending in DB, mark cancelled.
        row = await self._db.fetch_one(
            "SELECT status FROM task_executions WHERE id = ?", (execution_id,)
        )
        if row is None:
            return False
        if row["status"] in ("running", "pending"):
            now = time.time()
            await self._db.execute(
                "UPDATE task_executions SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
                ("cancelled", now, "Cancelled (orphan execution)", execution_id),
            )
            await self._db.execute(
                "UPDATE execution_step_logs SET status = ?, completed_at = ?, error_msg = ? WHERE execution_id = ? AND status = ?",
                ("cancelled", now, "Cancelled (orphan execution)", execution_id, "running"),
            )
            return True
        return False

    async def list_executions(
        self,
        limit: int = 50,
        offset: int = 0,
        start_ts: float | None = None,
        end_ts: float | None = None,
        order: str = "desc",
    ) -> dict:
        where = " WHERE 1=1"
        params: list = []
        if start_ts is not None:
            where += " AND e.started_at >= ?"
            params.append(start_ts)
        if end_ts is not None:
            where += " AND e.started_at <= ?"
            params.append(end_ts)

        count_row = await self._db.fetch_one(
            f"SELECT COUNT(*) AS n FROM task_executions e{where}", tuple(params)
        )
        total = count_row["n"] if count_row else 0

        direction = "ASC" if order.lower() == "asc" else "DESC"
        sql = (
            "SELECT e.*, t.name AS template_name, t.steps_json AS template_steps_json "
            "FROM task_executions e "
            "LEFT JOIN task_templates t ON e.task_template_id = t.id"
            f"{where} ORDER BY e.started_at {direction} LIMIT ? OFFSET ?"
        )
        items = await self._db.fetch_all(sql, tuple(params + [limit, offset]))
        for it in items:
            it["robot_id"] = self._derive_robot_id(it.pop("template_steps_json", None))
        return {"items": items, "total": total}

    @staticmethod
    def _derive_robot_id(steps_json) -> str | None:
        if not steps_json:
            return None
        try:
            steps = json.loads(steps_json)
        except (json.JSONDecodeError, TypeError):
            return None
        for step in steps:
            cfg = step.get("config") or {}
            rid = cfg.get("robot_id")
            if rid:
                return rid
        return None

    async def get_execution(self, execution_id: int) -> dict | None:
        execution = await self._db.fetch_one(
            "SELECT e.*, t.name AS template_name, t.steps_json AS template_steps_json "
            "FROM task_executions e "
            "LEFT JOIN task_templates t ON e.task_template_id = t.id "
            "WHERE e.id = ?",
            (execution_id,),
        )
        if not execution:
            return None
        steps = await self._db.fetch_all(
            "SELECT * FROM execution_step_logs WHERE execution_id = ? ORDER BY step_order",
            (execution_id,),
        )
        # Merge template step definitions (for label) into log entries
        template_steps = []
        if execution.get("template_steps_json"):
            try:
                template_steps = json.loads(execution["template_steps_json"])
            except Exception:
                template_steps = []
        template_by_id = {s.get("id"): s for s in template_steps}

        merged = []
        # Include logged steps in order
        logged_ids = set()
        for s in steps:
            tpl = template_by_id.get(s["step_id"], {})
            merged.append({
                **s,
                "label": tpl.get("label", s["step_id"]),
                "config": tpl.get("config", {}),
            })
            logged_ids.add(s["step_id"])
        # Include not-yet-started template steps as pending
        for i, tpl in enumerate(template_steps):
            if tpl.get("id") not in logged_ids:
                merged.append({
                    "id": None,
                    "execution_id": execution_id,
                    "step_order": i + 1,
                    "step_id": tpl.get("id"),
                    "step_type": tpl.get("type"),
                    "step_config_json": json.dumps(tpl.get("config", {})),
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "error_msg": None,
                    "sub_step_results_json": None,
                    "label": tpl.get("label", tpl.get("id", "")),
                    "config": tpl.get("config", {}),
                })
        merged.sort(key=lambda x: x.get("step_order") or 0)
        execution["steps"] = merged
        return execution

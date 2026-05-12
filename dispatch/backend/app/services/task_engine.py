import json
import time
from pydantic import BaseModel
from app.core.database import Database
from furance_shared.protocol.http_schema import ApiResponse


class TaskStep(BaseModel):
    order: int
    action: str
    params: dict = {}


class TaskTemplate(BaseModel):
    id: str
    name: str
    steps: list[TaskStep]


class TaskEngine:
    def __init__(self, db: Database | None = None, db_path: str = "./data/dispatch.db"):
        self._db = db or Database(db_path)

    async def _ensure_db(self):
        if not self._db._db:
            await self._db.init()

    # ── Template CRUD ──

    async def create_template(self, template: TaskTemplate) -> dict:
        await self._ensure_db()
        now = time.time()
        await self._db.execute(
            "INSERT OR REPLACE INTO task_templates (id, name, steps_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (template.id, template.name, template.model_dump_json(exclude={"id", "name"}), now, now),
        )
        return {"id": template.id, "name": template.name}

    async def list_templates(self) -> list[dict]:
        await self._ensure_db()
        return await self._db.fetch_all("SELECT * FROM task_templates")

    async def get_template(self, template_id: str) -> dict | None:
        await self._ensure_db()
        return await self._db.fetch_one("SELECT * FROM task_templates WHERE id = ?", (template_id,))

    async def update_template(self, template: TaskTemplate) -> dict | None:
        await self._ensure_db()
        existing = await self._db.fetch_one("SELECT id FROM task_templates WHERE id = ?", (template.id,))
        if not existing:
            return None
        now = time.time()
        await self._db.execute(
            "UPDATE task_templates SET name = ?, steps_json = ?, updated_at = ? WHERE id = ?",
            (template.name, template.model_dump_json(exclude={"id", "name"}), now, template.id),
        )
        return {"id": template.id, "name": template.name}

    async def delete_template(self, template_id: str) -> bool:
        await self._ensure_db()
        existing = await self._db.fetch_one("SELECT id FROM task_templates WHERE id = ?", (template_id,))
        if not existing:
            return False
        await self._db.execute("DELETE FROM task_templates WHERE id = ?", (template_id,))
        return True

    # ── Execution ──

    async def execute(self, template_id: str, robot_id: str, robot_proxy, sampler_service) -> dict:
        await self._ensure_db()
        template_row = await self._db.fetch_one(
            "SELECT * FROM task_templates WHERE id = ?", (template_id,)
        )
        if not template_row:
            return {"status": "error", "error_msg": f"Template {template_id} not found"}

        steps_data = json.loads(template_row["steps_json"])
        steps = steps_data.get("steps", [])

        now = time.time()
        await self._db.execute(
            "INSERT INTO task_executions (task_template_id, robot_id, status, started_at) VALUES (?, ?, ?, ?)",
            (template_id, robot_id, "running", now),
        )
        execution = await self._db.fetch_one(
            "SELECT * FROM task_executions WHERE task_template_id = ? AND robot_id = ? ORDER BY id DESC LIMIT 1",
            (template_id, robot_id),
        )
        execution_id = execution["id"]

        for step in sorted(steps, key=lambda s: s.get("order", 0)):
            step_now = time.time()
            action = step["action"]
            params = step.get("params", {})
            result = None
            step_status = "completed"

            try:
                if action.startswith("robot."):
                    action_name = action.split(".", 1)[1]
                    path = f"/api/v1/robot/{robot_id}/{action_name}"
                    resp = await robot_proxy.forward(robot_id, path, params if params else None)
                    step_status = "completed" if resp.code == 0 else "failed"
                    result = resp.model_dump()
                elif action.startswith("sampler."):
                    action_name = action.split(".", 1)[1]
                    if action_name == "start":
                        resp = await sampler_service.start()
                    elif action_name == "stop":
                        resp = await sampler_service.stop()
                    else:
                        resp = ApiResponse(code=3002, message=f"Unknown sampler action: {action_name}")
                    step_status = "completed" if resp.code == 0 else "failed"
                    result = resp.model_dump()
                elif action == "wait_sampler_complete":
                    resp = await sampler_service.wait_complete()
                    step_status = "completed" if resp.code == 0 else "failed"
                    result = resp.model_dump()
                elif action == "delay":
                    import asyncio
                    delay_secs = params.get("seconds", 1.0)
                    await asyncio.sleep(delay_secs)
                    step_status = "completed"
                    result = {"delayed": delay_secs}
            except Exception as e:
                step_status = "failed"
                result = {"error": str(e)}

            await self._db.execute(
                "INSERT INTO task_step_logs (execution_id, step_order, action, params_json, result_json, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (execution_id, step["order"], action, json.dumps(params), json.dumps(result), step_status, step_now, time.time()),
            )

            if step_status == "failed":
                await self._db.execute(
                    "UPDATE task_executions SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
                    ("failed", time.time(), f"Step {step['order']} ({action}) failed", execution_id),
                )
                return {"status": "failed", "execution_id": execution_id, "error_msg": f"Step {step['order']} failed"}

        await self._db.execute(
            "UPDATE task_executions SET status = ?, completed_at = ? WHERE id = ?",
            ("completed", time.time(), execution_id),
        )
        return {"status": "completed", "execution_id": execution_id}

    async def cancel_execution(self, execution_id: int) -> bool:
        await self._ensure_db()
        execution = await self._db.fetch_one("SELECT * FROM task_executions WHERE id = ?", (execution_id,))
        if not execution or execution["status"] != "running":
            return False
        now = time.time()
        await self._db.execute(
            "UPDATE task_executions SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
            ("cancelled", now, "Cancelled by user", execution_id),
        )
        return True

    async def list_executions(self, limit: int = 50) -> list[dict]:
        await self._ensure_db()
        return await self._db.fetch_all("SELECT * FROM task_executions ORDER BY id DESC LIMIT ?", (limit,))

    async def get_execution(self, execution_id: int) -> dict | None:
        await self._ensure_db()
        execution = await self._db.fetch_one("SELECT * FROM task_executions WHERE id = ?", (execution_id,))
        if not execution:
            return None
        steps = await self._db.fetch_all("SELECT * FROM task_step_logs WHERE execution_id = ? ORDER BY step_order", (execution_id,))
        execution["steps"] = steps
        return execution

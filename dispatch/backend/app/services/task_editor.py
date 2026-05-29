import json
import time
from app.core.database import Database
from app.models.task import TaskTemplate, TaskStep


class TaskEditor:
    def __init__(self, db: Database):
        self._db = db

    async def create(self, template: TaskTemplate) -> dict:
        now = time.time()
        steps_json = json.dumps([s.model_dump() for s in template.steps], ensure_ascii=False)
        await self._db.execute(
            "INSERT INTO task_templates (id, name, description, steps_json, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (template.id, template.name, template.description, steps_json, template.version, now, now),
        )
        return {"id": template.id, "name": template.name}

    async def list_all(self) -> list[dict]:
        rows = await self._db.fetch_all("SELECT * FROM task_templates ORDER BY updated_at DESC")
        for row in rows:
            row["robot_id"] = self._derive_robot_id(row.get("steps_json", "[]"))
        return rows

    @staticmethod
    def _derive_robot_id(steps_json: str) -> str | None:
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

    async def get(self, template_id: str) -> dict | None:
        return await self._db.fetch_one("SELECT * FROM task_templates WHERE id = ?", (template_id,))

    async def update(self, template: TaskTemplate) -> dict | None:
        existing = await self._db.fetch_one("SELECT id FROM task_templates WHERE id = ?", (template.id,))
        if not existing:
            return None
        now = time.time()
        steps_json = json.dumps([s.model_dump() for s in template.steps], ensure_ascii=False)
        await self._db.execute(
            "UPDATE task_templates SET name = ?, description = ?, steps_json = ?, version = ?, updated_at = ? WHERE id = ?",
            (template.name, template.description, steps_json, template.version, now, template.id),
        )
        return {"id": template.id, "name": template.name}

    async def delete(self, template_id: str) -> bool:
        existing = await self._db.fetch_one("SELECT id FROM task_templates WHERE id = ?", (template_id,))
        if not existing:
            return False
        await self._db.execute("DELETE FROM task_templates WHERE id = ?", (template_id,))
        return True

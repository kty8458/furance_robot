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
        return await self._db.fetch_all("SELECT * FROM task_templates ORDER BY updated_at DESC")

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

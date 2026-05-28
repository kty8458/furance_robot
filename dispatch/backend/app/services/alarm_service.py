import json
import time
import uuid
import logging
from app.core.database import Database
from app.models.alarm import AlarmLevel, AlarmRule

logger = logging.getLogger(__name__)


class AlarmService:
    def __init__(self, db: Database, task_executor=None):
        self._db = db
        self._task_executor = task_executor

    async def create_alarm(self, robot_id: str, source: str, level: str, category: str,
                           title: str, message: str) -> dict:
        existing = await self._db.fetch_one(
            "SELECT id FROM alarms WHERE robot_id = ? AND title = ? AND ack_status = 'unack'",
            (robot_id, title),
        )
        if existing:
            return {"id": existing["id"], "duplicate": True}

        alarm_id = str(uuid.uuid4())
        now = time.time()
        await self._db.execute(
            "INSERT INTO alarms (id, robot_id, source, level, category, title, message, ack_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (alarm_id, robot_id, source, level, category, title, message, "unack", now),
        )
        if level == AlarmLevel.CRITICAL and self._task_executor:
            self._task_executor.notify_critical_alarm()
        return {
            "id": alarm_id, "robot_id": robot_id, "source": source,
            "level": level, "category": category, "title": title, "message": message,
        }

    async def list_alarms(self, level: str = None, robot_id: str = None,
                          ack_status: str = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM alarms WHERE 1=1"
        params = []
        if level:
            query += " AND level = ?"
            params.append(level)
        if robot_id:
            query += " AND robot_id = ?"
            params.append(robot_id)
        if ack_status:
            query += " AND ack_status = ?"
            params.append(ack_status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return await self._db.fetch_all(query, tuple(params))

    async def ack_alarm(self, alarm_id: str, ack_by: str = "operator") -> bool:
        existing = await self._db.fetch_one("SELECT id FROM alarms WHERE id = ?", (alarm_id,))
        if not existing:
            return False
        now = time.time()
        await self._db.execute(
            "UPDATE alarms SET ack_status = ?, ack_by = ?, ack_at = ? WHERE id = ?",
            ("acked", ack_by, now, alarm_id),
        )
        return True

    async def check_conditions(self, status_data: dict) -> list[dict]:
        rules = await self._db.fetch_all("SELECT * FROM alarm_rules WHERE enabled = 1")
        triggered = []
        for rule in rules:
            condition = json.loads(rule["condition_json"])
            field = condition.get("field", "")
            operator = condition.get("operator", "<")
            threshold = condition.get("value", 0)
            current = self._get_nested_value(status_data, field)
            if current is None:
                continue
            if self._evaluate(current, operator, threshold):
                alarm = await self.create_alarm(
                    robot_id=status_data.get("robot_id", ""),
                    source="robot",
                    level=rule["level"],
                    category=rule["category"],
                    title=rule["name"],
                    message=f"{field} = {current}, threshold {operator} {threshold}",
                )
                triggered.append(alarm)
        return triggered

    async def list_rules(self) -> list[dict]:
        return await self._db.fetch_all("SELECT * FROM alarm_rules ORDER BY id")

    async def create_rule(self, rule: AlarmRule) -> dict:
        now = time.time()
        await self._db.execute(
            "INSERT INTO alarm_rules (name, category, level, condition_json, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (rule.name, rule.category, rule.level, json.dumps(rule.condition_json), int(rule.enabled), now),
        )
        rows = await self._db.fetch_all("SELECT last_insert_rowid() as id")
        return {"id": rows[0]["id"], "name": rule.name}

    async def update_rule(self, rule_id: int, rule: AlarmRule) -> bool:
        existing = await self._db.fetch_one("SELECT id FROM alarm_rules WHERE id = ?", (rule_id,))
        if not existing:
            return False
        await self._db.execute(
            "UPDATE alarm_rules SET name = ?, category = ?, level = ?, condition_json = ?, enabled = ? WHERE id = ?",
            (rule.name, rule.category, rule.level, json.dumps(rule.condition_json), int(rule.enabled), rule_id),
        )
        return True

    async def delete_rule(self, rule_id: int) -> bool:
        existing = await self._db.fetch_one("SELECT id FROM alarm_rules WHERE id = ?", (rule_id,))
        if not existing:
            return False
        await self._db.execute("DELETE FROM alarm_rules WHERE id = ?", (rule_id,))
        return True

    @staticmethod
    def _get_nested_value(data: dict, field: str):
        parts = field.split(".")
        current = data
        for p in parts:
            if isinstance(current, dict):
                current = current.get(p)
            else:
                return None
        return current

    @staticmethod
    def _evaluate(current, operator: str, threshold) -> bool:
        ops = {
            "<": lambda a, b: a < b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            ">=": lambda a, b: a >= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        fn = ops.get(operator)
        if fn is None:
            return False
        try:
            return fn(float(current), float(threshold))
        except (ValueError, TypeError):
            return fn(str(current), str(threshold))

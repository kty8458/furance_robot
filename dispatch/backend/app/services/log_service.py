import time
from app.core.database import Database


class LogService:
    def __init__(self, db: Database):
        self._db = db

    async def list_logs(self, level: str = None, source: str = None,
                        robot_id: str = None, limit: int = 200) -> list[dict]:
        query = "SELECT * FROM operation_logs WHERE 1=1"
        params = []
        if level:
            query += " AND level = ?"
            params.append(level)
        if source:
            query += " AND source = ?"
            params.append(source)
        if robot_id:
            query += " AND robot_id = ?"
            params.append(robot_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return await self._db.fetch_all(query, tuple(params))

    async def add_log(self, source: str, level: str, message: str,
                      robot_id: str = "", node: str = ""):
        now = time.time()
        await self._db.execute(
            "INSERT INTO operation_logs (source, robot_id, level, node, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (source, robot_id, level, node, message, now),
        )

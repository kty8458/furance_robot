import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS robots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    control_url TEXT NOT NULL,
    ws_url TEXT NOT NULL,
    status TEXT DEFAULT 'offline',
    last_heartbeat REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    steps_json TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_template_id TEXT NOT NULL,
    trigger_type TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'pending',
    started_at REAL,
    completed_at REAL,
    error_msg TEXT,
    current_step_id TEXT
);

CREATE TABLE IF NOT EXISTS execution_step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    step_id TEXT NOT NULL,
    step_type TEXT NOT NULL,
    step_config_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    sub_step_results_json TEXT,
    started_at REAL,
    completed_at REAL,
    error_msg TEXT
);

CREATE TABLE IF NOT EXISTS alarms (
    id TEXT PRIMARY KEY,
    robot_id TEXT DEFAULT '',
    source TEXT DEFAULT '',
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    ack_status TEXT DEFAULT 'unack',
    ack_by TEXT DEFAULT '',
    ack_at REAL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alarm_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    level TEXT NOT NULL,
    condition_json TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    robot_id TEXT DEFAULT '',
    level TEXT NOT NULL,
    node TEXT DEFAULT '',
    message TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS robot_status (
    robot_id TEXT PRIMARY KEY,
    status_json TEXT DEFAULT '{}',
    updated_at REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sampler_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'idle',
    progress INTEGER DEFAULT 0,
    status_json TEXT DEFAULT '{}',
    last_update REAL NOT NULL
);
"""


class Database:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    async def execute(self, query: str, params: tuple = ()):
        await self._db.execute(query, params)
        await self._db.commit()

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        cursor = await self._db.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row else None
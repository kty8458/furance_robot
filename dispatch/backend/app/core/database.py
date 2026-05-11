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
    steps_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_template_id TEXT NOT NULL,
    robot_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    started_at REAL,
    completed_at REAL,
    error_msg TEXT
);

CREATE TABLE IF NOT EXISTS task_step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    action TEXT NOT NULL,
    params_json TEXT,
    result_json TEXT,
    status TEXT DEFAULT 'pending',
    started_at REAL,
    completed_at REAL
);

CREATE TABLE IF NOT EXISTS sampler_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'idle',
    progress INTEGER DEFAULT 0,
    last_update REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS robot_status (
    robot_id TEXT PRIMARY KEY,
    position_json TEXT DEFAULT '{}',
    gripper_json TEXT DEFAULT '{}',
    arm_json TEXT DEFAULT '{}',
    battery INTEGER DEFAULT 0,
    charging INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 0,
    error_code INTEGER DEFAULT 0,
    task_status TEXT DEFAULT 'idle',
    updated_at REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS l2_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    l2_request_id TEXT,
    task_template_id TEXT,
    task_execution_id INTEGER,
    command_json TEXT,
    status TEXT DEFAULT 'pending',
    received_at REAL,
    completed_at REAL,
    response_json TEXT
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
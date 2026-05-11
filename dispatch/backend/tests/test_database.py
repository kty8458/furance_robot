import pytest
from app.core.database import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_database_init(db):
    assert db is not None


@pytest.mark.asyncio
async def test_insert_and_query_robot_status(db):
    await db.execute(
        "INSERT INTO robot_status (robot_id, position_json, battery, task_status) VALUES (?, ?, ?, ?)",
        ("robot_001", '{"x":1.0}', 85, "idle"),
    )
    rows = await db.fetch_all("SELECT * FROM robot_status WHERE robot_id = ?", ("robot_001",))
    assert len(rows) == 1
    assert rows[0]["robot_id"] == "robot_001"
    assert rows[0]["battery"] == 85
import pytest
import json
import time
from unittest.mock import AsyncMock
from app.core.database import Database
from app.services.task_engine import TaskEngine, TaskTemplate, TaskStep
from furance_shared.protocol.http_schema import ApiResponse


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


@pytest.fixture
def task_engine(db):
    return TaskEngine(db=db)


@pytest.mark.asyncio
async def test_create_template(task_engine):
    template = TaskTemplate(
        id="sample_delivery",
        name="取样送样流程",
        steps=[
            TaskStep(order=1, action="robot.home", params={}),
            TaskStep(order=2, action="robot.move", params={"map_id": "map_001", "waypoint_id": "wp_01", "speed": 0.5}),
        ],
    )
    result = await task_engine.create_template(template)
    assert result["id"] == "sample_delivery"
    templates = await task_engine.list_templates()
    assert len(templates) == 1
    assert templates[0]["name"] == "取样送样流程"


@pytest.mark.asyncio
async def test_get_template(task_engine):
    template = TaskTemplate(id="t1", name="Test", steps=[TaskStep(order=1, action="robot.home", params={})])
    await task_engine.create_template(template)
    result = await task_engine.get_template("t1")
    assert result is not None
    assert result["name"] == "Test"
    assert await task_engine.get_template("nonexistent") is None


@pytest.mark.asyncio
async def test_update_template(task_engine):
    template = TaskTemplate(id="t1", name="Original", steps=[TaskStep(order=1, action="robot.home", params={})])
    await task_engine.create_template(template)
    updated = TaskTemplate(id="t1", name="Updated", steps=[TaskStep(order=1, action="robot.move", params={})])
    result = await task_engine.update_template(updated)
    assert result["name"] == "Updated"
    row = await task_engine.get_template("t1")
    assert row["name"] == "Updated"


@pytest.mark.asyncio
async def test_delete_template(task_engine):
    template = TaskTemplate(id="t1", name="Test", steps=[TaskStep(order=1, action="robot.home", params={})])
    await task_engine.create_template(template)
    assert await task_engine.delete_template("t1") is True
    assert await task_engine.get_template("t1") is None
    assert await task_engine.delete_template("nonexistent") is False


@pytest.mark.asyncio
async def test_execute_template(task_engine):
    template = TaskTemplate(
        id="simple_home",
        name="归零流程",
        steps=[TaskStep(order=1, action="robot.home", params={})],
    )
    await task_engine.create_template(template)

    mock_proxy = AsyncMock()
    mock_proxy.forward = AsyncMock(return_value=ApiResponse(code=0))
    mock_sampler = AsyncMock()
    mock_sampler.start = AsyncMock(return_value=ApiResponse(code=0))

    result = await task_engine.execute("simple_home", "robot_001", mock_proxy, mock_sampler)
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_nonexistent_template(task_engine):
    mock_proxy = AsyncMock()
    mock_sampler = AsyncMock()
    result = await task_engine.execute("nonexistent", "robot_001", mock_proxy, mock_sampler)
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_cancel_execution(task_engine):
    template = TaskTemplate(id="t1", name="Test", steps=[TaskStep(order=1, action="robot.home", params={})])
    await task_engine.create_template(template)

    # Insert a running execution directly
    now = time.time()
    await task_engine._db.execute(
        "INSERT INTO task_executions (task_template_id, robot_id, status, started_at) VALUES (?, ?, ?, ?)",
        ("t1", "robot_001", "running", now),
    )
    assert await task_engine.cancel_execution(1) is True
    assert await task_engine.cancel_execution(999) is False


@pytest.mark.asyncio
async def test_list_and_get_executions(task_engine):
    template = TaskTemplate(id="t1", name="Test", steps=[TaskStep(order=1, action="robot.home", params={})])
    await task_engine.create_template(template)

    now = time.time()
    await task_engine._db.execute(
        "INSERT INTO task_executions (task_template_id, robot_id, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?)",
        ("t1", "robot_001", "completed", now, now),
    )
    executions = await task_engine.list_executions()
    assert len(executions) == 1

    execution = await task_engine.get_execution(1)
    assert execution is not None
    assert execution["status"] == "completed"
    assert "steps" in execution

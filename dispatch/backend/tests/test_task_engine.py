import pytest
import json
import time
from app.services.task_engine import TaskEngine, TaskTemplate, TaskStep
from unittest.mock import AsyncMock
from furance_shared.protocol.http_schema import ApiResponse


@pytest.fixture
def task_engine(tmp_path):
    engine = TaskEngine(db_path=str(tmp_path / "test.db"))
    return engine


@pytest.mark.asyncio
async def test_create_template(task_engine):
    await task_engine.init_db()
    template = TaskTemplate(
        id="sample_delivery",
        name="取样送样流程",
        steps=[
            TaskStep(order=1, action="robot.home", params={}),
            TaskStep(order=2, action="robot.move", params={"map_id": "map_001", "waypoint_id": "wp_01", "speed": 0.5}),
        ],
    )
    await task_engine.save_template(template)
    templates = await task_engine.list_templates()
    assert len(templates) == 1
    assert templates[0]["name"] == "取样送样流程"


@pytest.mark.asyncio
async def test_execute_template(task_engine):
    await task_engine.init_db()
    template = TaskTemplate(
        id="simple_home",
        name="归零流程",
        steps=[TaskStep(order=1, action="robot.home", params={})],
    )
    await task_engine.save_template(template)

    mock_proxy = AsyncMock()
    mock_proxy.forward = AsyncMock(return_value=ApiResponse(code=0))
    mock_sampler = AsyncMock()
    mock_sampler.start = AsyncMock(return_value=ApiResponse(code=0))

    result = await task_engine.execute("simple_home", "robot_001", mock_proxy, mock_sampler)
    assert result["status"] == "completed"
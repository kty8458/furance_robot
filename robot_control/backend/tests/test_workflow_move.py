"""工作流移动步骤执行测试: 组合路径按 name 下发, 普通任务按 tasks 下发."""
from unittest.mock import AsyncMock

import pytest

from app.services.workflow_service import WorkflowService
from furance_shared.models.workflow import WorkflowStep


def _make_service(chassis) -> WorkflowService:
    return WorkflowService(chassis_client=chassis, workflow_dir="/tmp/test_workflows")


def _make_chassis() -> AsyncMock:
    chassis = AsyncMock()
    chassis.start_task = AsyncMock(return_value={"success": True, "successed": True, "msg": "ok"})
    chassis.is_task_finished = AsyncMock(return_value={"success": True, "data": True})
    return chassis


def _move_step(config: dict) -> WorkflowStep:
    return WorkflowStep(id="s1", type="move", label="移动", config=config)


@pytest.mark.asyncio
async def test_execute_move_combined_path_sent_by_name():
    """组合路径: task_body 按 name 下发, tasks 为空, 由底盘执行已保存队列."""
    chassis = _make_chassis()
    service = _make_service(chassis)
    step = _move_step({
        "move_source": "manual",
        "map_name": "map1",
        "point_name": "组合路径1",
        "path_type": "CombinedPathTask",
    })

    result = await service._execute_move(step, {}, {}, "robot_001")

    assert result.success
    body = chassis.start_task.call_args[0][0]
    assert body == {"map_name": "map1", "name": "组合路径1", "loop": False, "tasks": []}


@pytest.mark.asyncio
async def test_execute_move_point_task_sent_by_tasks():
    """普通导航点: 仍按 tasks 数组下发, 不受组合路径改动影响."""
    chassis = _make_chassis()
    service = _make_service(chassis)
    step = _move_step({
        "move_source": "manual",
        "map_name": "map1",
        "point_name": "A点",
        "path_type": "NavigationPointTask",
    })

    result = await service._execute_move(step, {}, {}, "robot_001")

    assert result.success
    body = chassis.start_task.call_args[0][0]
    assert body == {
        "map_name": "map1",
        "loop": False,
        "tasks": [{
            "name": "NavigationPointTask",
            "start_param": {"map_name": "map1", "position_name": "A点", "path_name": ""},
        }],
    }

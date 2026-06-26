from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/navigation", tags=["navigation"])


def _get_chassis(request: Request):
    return request.app.state.chassis_client


class NavigationTask(BaseModel):
    name: str
    start_param: dict


class TaskStartRequest(BaseModel):
    map_name: str
    name: str = ""
    loop: bool = False
    loop_count: int = 0
    tasks: list[NavigationTask]


class RechargeRequest(BaseModel):
    map_name: str
    point_name: str


@router.post("/token/refresh", response_model=ApiResponse)
async def refresh_token(request: Request):
    chassis = _get_chassis(request)
    result = await chassis.authenticate(force=True)
    return ApiResponse(data=result)


@router.get("/maps", response_model=ApiResponse)
async def get_maps(request: Request):
    chassis = _get_chassis(request)
    result = await chassis.get_maps()
    if not result.get("success"):
        return ApiResponse(code=1005, message=result.get("message", "获取地图列表失败"))
    return ApiResponse(data=result.get("data"))


@router.get("/positions", response_model=ApiResponse)
async def get_positions(request: Request, map_name: str = Query(...), type: str = Query("")):
    chassis = _get_chassis(request)
    result = await chassis.get_positions(map_name, type)
    if not result.get("success"):
        return ApiResponse(code=1005, message=result.get("message", "获取导航点失败"))
    return ApiResponse(data=result.get("data"))


@router.get("/graph-paths", response_model=ApiResponse)
async def get_graph_paths(request: Request, map_name: str = Query(...)):
    chassis = _get_chassis(request)
    result = await chassis.get_graph_paths(map_name)
    if not result.get("success"):
        return ApiResponse(code=1005, message=result.get("message", "获取手绘路径失败"))
    return ApiResponse(data=result.get("data"))


@router.get("/record-paths", response_model=ApiResponse)
async def get_record_paths(request: Request, map_name: str = Query(...)):
    chassis = _get_chassis(request)
    result = await chassis.get_record_paths(map_name)
    if not result.get("success"):
        return ApiResponse(code=1005, message=result.get("message", "获取录制路径失败"))
    return ApiResponse(data=result.get("data"))


@router.post("/task/start", response_model=ApiResponse)
async def start_task(request: Request, body: TaskStartRequest):
    chassis = _get_chassis(request)
    result = await chassis.start_task(body.model_dump())
    if not result.get("success"):
        return ApiResponse(code=2006, message=result.get("message", "任务启动失败"))
    return ApiResponse(data=result.get("data"))


@router.post("/task/stop", response_model=ApiResponse)
async def stop_task(request: Request):
    chassis = _get_chassis(request)
    result = await chassis.stop_task()
    if not result.get("success"):
        return ApiResponse(code=2006, message=result.get("message", "任务停止失败"))
    return ApiResponse(data=result.get("data"))


@router.get("/task/status", response_model=ApiResponse)
async def task_status(request: Request):
    """是否有任务正在执行 (data=True 表示空闲，data=False 表示有任务)."""
    chassis = _get_chassis(request)
    result = await chassis.is_task_finished()
    if not result.get("success"):
        return ApiResponse(code=1005, message=result.get("message", "获取任务状态失败"))
    return ApiResponse(data=result.get("data"))


@router.get("/task/queue-status", response_model=ApiResponse)
async def queue_status(request: Request):
    """任务队列执行状态 (data=1 正在执行, data=0 没有执行, msg='不能到达' 表示出错)."""
    chassis = _get_chassis(request)
    result = await chassis.is_queue_finished()
    if not result.get("success"):
        return ApiResponse(code=1005, message=result.get("message", "获取队列状态失败"))
    return ApiResponse(data=result.get("data"), message=result.get("message", "ok"))


@router.post("/recharge", response_model=ApiResponse)
async def recharge(request: Request, body: RechargeRequest):
    chassis = _get_chassis(request)
    result = await chassis.recharge(body.map_name, body.point_name)
    if not result.get("success"):
        return ApiResponse(code=2006, message=result.get("message", "回充指令失败"))
    return ApiResponse(data=result.get("data"))


class MoveWithParamsRequest(BaseModel):
    linear_velocity: float = 0.0   # m/s [-0.5, 0.5]
    slip_angle: float = 0.0        # rad [-2.14, 2.14] (四转四驱底盘横移用)
    angular_velocity: float = 0.0  # rad/s [-0.5, 0.5]
    target_distance: float = 0.0   # m
    target_angle: float = 0.0      # rad [0, 3.14]
    mode: int = 1                  # 1=定距离, 2=定角度


@router.post("/move_with_params", response_model=ApiResponse)
async def move_with_params(request: Request, body: MoveWithParamsRequest):
    """定距离/定角度移动控制."""
    chassis = _get_chassis(request)
    result = await chassis.move_with_params(
        linear_velocity=body.linear_velocity,
        slip_angle=body.slip_angle,
        angular_velocity=body.angular_velocity,
        target_distance=body.target_distance,
        target_angle=body.target_angle,
        mode=body.mode,
    )
    if not result.get("success"):
        return ApiResponse(code=2007, message=result.get("message", "定距离/定角度移动失败"))
    return ApiResponse(data=result.get("data"))


@router.post("/cancel_move_with_params", response_model=ApiResponse)
async def cancel_move_with_params(request: Request):
    """取消正在执行的定距离/定角度移动."""
    chassis = _get_chassis(request)
    result = await chassis.cancel_move_with_params()
    if not result.get("success"):
        return ApiResponse(code=2008, message=result.get("message", "取消移动失败"))
    return ApiResponse(data=result.get("data"))

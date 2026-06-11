from fastapi import APIRouter, Request
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/robot/{robot_id}/camera", tags=["camera"])


def _get_client(request: Request):
    return request.app.state.ros2.camera_client


@router.get("/list", response_model=ApiResponse)
async def list_cameras(robot_id: str, request: Request):
    """获取所有已配置相机的列表和信息。"""
    result = await _get_client(request).get_camera_list()
    if not result.get("success"):
        return ApiResponse(code=3001, message=result.get("message", "Failed to get camera list"))
    return ApiResponse(data=result.get("cameras", []))


@router.post("/stream/start", response_model=ApiResponse)
async def start_stream(robot_id: str, req: dict, request: Request):
    """启动相机帧采集: {"camera_id": "head", "stream_type": "raw"}"""
    camera_id = req.get("camera_id", "head")
    stream_type = req.get("stream_type", "raw")
    result = await _get_client(request).start_stream(camera_id, stream_type)
    return ApiResponse(data=result)


@router.post("/stream/stop", response_model=ApiResponse)
async def stop_stream(robot_id: str, req: dict, request: Request):
    """停止相机帧采集: {"camera_id": "head"}"""
    camera_id = req.get("camera_id", "head")
    result = await _get_client(request).stop_stream(camera_id)
    return ApiResponse(data=result)


@router.post("/detect", response_model=ApiResponse)
async def detect(robot_id: str, req: dict, request: Request):
    """执行视觉检测: {"camera_id": "head", "scene": "grasp_top"}"""
    camera_id = req.get("camera_id", "head")
    scene = req.get("scene", "")
    result = await _get_client(request).detect_grasp_pose(camera_id, scene)
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "Detection failed"))
    return ApiResponse(data=result.get("data", result))

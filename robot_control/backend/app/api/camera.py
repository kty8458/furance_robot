from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/robot/{robot_id}/camera", tags=["camera"])


def _get_client(request: Request):
    return request.app.state.ros2.camera_client


@router.post("/stream/start", response_model=ApiResponse)
async def start_stream(robot_id: str, req: dict, request: Request):
    """Start streaming: {"camera_id": "camera_1", "stream_type": "raw|grayscale|annotated"}"""
    camera_id = req.get("camera_id", "camera_1")
    stream_type = req.get("stream_type", "raw")
    result = await _get_client(request).start_stream(camera_id, stream_type)
    return ApiResponse(data=result)


@router.post("/stream/stop", response_model=ApiResponse)
async def stop_stream(robot_id: str, request: Request):
    """Stop the currently active camera stream."""
    client = _get_client(request)
    # Stop all known cameras
    for cid in ("camera_1", "camera_2", "camera_3"):
        await client.stop_stream(cid)
    return ApiResponse(data={"success": True})


@router.get("/frame")
async def get_frame(robot_id: str, camera_id: str = "camera_1", request: Request = None):
    """Get the latest JPEG frame from the active camera stream."""
    client = _get_client(request)
    frame = await client.get_frame(camera_id)
    if frame is None:
        return ApiResponse(code=1002, message="No frame available")
    return StreamingResponse(
        iter([frame]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/detect", response_model=ApiResponse)
async def detect(robot_id: str, req: dict, request: Request):
    """Run vision detection: {"camera_id": "camera_1", "scene": "grasp_top"}"""
    camera_id = req.get("camera_id", "camera_1")
    scene = req.get("scene", "")
    result = await _get_client(request).detect_grasp_pose(camera_id, scene)
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "Detection failed"))
    return ApiResponse(data=result.get("data", result))

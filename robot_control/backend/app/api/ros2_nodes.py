from fastapi import APIRouter, Request
from furance_shared.protocol.http_schema import ApiResponse
from app.services.ros2_manager import Ros2Manager

router = APIRouter(prefix="/api/v1/ros2", tags=["ros2"])


def _get_manager(request: Request) -> Ros2Manager:
    return Ros2Manager(
        ros2_client=request.app.state.ros2.service_client,
        launch_manager=request.app.state.launch_manager,
    )


@router.get("/nodes", response_model=ApiResponse)
async def list_nodes(request: Request):
    manager = _get_manager(request)
    return await manager.list_nodes()


@router.post("/nodes/{node_name}/start", response_model=ApiResponse)
async def start_node(node_name: str, request: Request):
    manager = _get_manager(request)
    return await manager.start_node(node_name)


@router.post("/nodes/{node_name}/stop", response_model=ApiResponse)
async def stop_node(node_name: str, request: Request):
    manager = _get_manager(request)
    return await manager.stop_node(node_name)


@router.get("/nodes/{node_name}/status", response_model=ApiResponse)
async def node_status(node_name: str, request: Request):
    manager = _get_manager(request)
    return await manager.node_status(node_name)


@router.get("/launches", response_model=ApiResponse)
async def list_launches(request: Request):
    manager = _get_manager(request)
    return await manager.list_launches()


@router.post("/launches/{name}/start", response_model=ApiResponse)
async def start_launch(name: str, request: Request):
    manager = _get_manager(request)
    return await manager.start_launch(name)


@router.post("/launches/{name}/stop", response_model=ApiResponse)
async def stop_launch(name: str, request: Request):
    manager = _get_manager(request)
    return await manager.stop_launch(name)


@router.get("/launches/{name}/status", response_model=ApiResponse)
async def launch_status(name: str, request: Request):
    manager = _get_manager(request)
    return await manager.launch_status(name)

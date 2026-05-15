from fastapi import APIRouter, Query, Request
from furance_shared.protocol.http_schema import ApiResponse
from app.services.ros2_manager import Ros2Manager

router = APIRouter(prefix="/api/v1/ros2", tags=["ros2"])


def _get_manager(request: Request) -> Ros2Manager:
    return Ros2Manager(ros2_client=request.app.state.ros2.service_client)


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


@router.get("/nodes/{node_name}/logs", response_model=ApiResponse)
async def node_logs(node_name: str, request: Request, tail: int = Query(200)):
    manager = _get_manager(request)
    return await manager.node_logs(node_name, tail)

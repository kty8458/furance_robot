from fastapi import APIRouter, Request
from furance_shared.protocol.http_schema import ApiResponse
from app.services.ros2_manager import Ros2Manager

router = APIRouter(prefix="/api/v1/ros2/nodes", tags=["ros2"])


@router.get("", response_model=ApiResponse)
async def list_nodes(request: Request):
    manager = Ros2Manager(request.app.state.ros2.service_client)
    return await manager.list_nodes()


@router.post("/{node_name}/start", response_model=ApiResponse)
async def start_node(node_name: str, request: Request):
    manager = Ros2Manager(request.app.state.ros2.service_client)
    return await manager.start_node(node_name)


@router.post("/{node_name}/stop", response_model=ApiResponse)
async def stop_node(node_name: str, request: Request):
    manager = Ros2Manager(request.app.state.ros2.service_client)
    return await manager.stop_node(node_name)


@router.get("/{node_name}/status", response_model=ApiResponse)
async def node_status(node_name: str, request: Request):
    manager = Ros2Manager(request.app.state.ros2.service_client)
    return await manager.node_status(node_name)

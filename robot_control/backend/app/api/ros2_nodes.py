from fastapi import APIRouter
from furance_shared.protocol.http_schema import ApiResponse
from app.services.ros2_manager import Ros2Manager
from app.ros2.service_client import MockRos2ServiceClient

router = APIRouter(prefix="/api/v1/ros2/nodes", tags=["ros2"])

_ros2_manager = Ros2Manager(MockRos2ServiceClient())


@router.get("", response_model=ApiResponse)
async def list_nodes():
    return await _ros2_manager.list_nodes()


@router.post("/{node_name}/start", response_model=ApiResponse)
async def start_node(node_name: str):
    return await _ros2_manager.start_node(node_name)


@router.post("/{node_name}/stop", response_model=ApiResponse)
async def stop_node(node_name: str):
    return await _ros2_manager.stop_node(node_name)


@router.get("/{node_name}/status", response_model=ApiResponse)
async def node_status(node_name: str):
    return await _ros2_manager.node_status(node_name)

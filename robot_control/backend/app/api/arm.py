from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/robot/{robot_id}/arm", tags=["arm"])

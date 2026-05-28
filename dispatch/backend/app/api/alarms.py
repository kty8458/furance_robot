from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from furance_shared.protocol.http_schema import ApiResponse
from app.models.alarm import AlarmRule

router = APIRouter(prefix="/api/v1/dispatch/alarms", tags=["alarms"])


@router.get("", response_model=ApiResponse)
async def list_alarms(
    request: Request,
    level: str = Query(None),
    robot_id: str = Query(None),
    ack_status: str = Query(None),
):
    alarms = await request.app.state.alarm_service.list_alarms(
        level=level, robot_id=robot_id, ack_status=ack_status,
    )
    return ApiResponse(data=alarms)


@router.post("/{alarm_id}/ack", response_model=ApiResponse)
async def ack_alarm(alarm_id: str, request: Request):
    ok = await request.app.state.alarm_service.ack_alarm(alarm_id)
    if not ok:
        return ApiResponse(code=3002, message="Alarm not found")
    return ApiResponse(data={"alarm_id": alarm_id, "ack_status": "acked"})


@router.get("/rules", response_model=ApiResponse)
async def list_rules(request: Request):
    rules = await request.app.state.alarm_service.list_rules()
    return ApiResponse(data=rules)


class RuleInput(BaseModel):
    name: str
    category: str
    level: str
    condition_json: dict
    enabled: bool = True


@router.post("/rules", response_model=ApiResponse)
async def create_rule(req: RuleInput, request: Request):
    rule = AlarmRule(
        name=req.name, category=req.category, level=req.level,
        condition_json=req.condition_json, enabled=req.enabled,
    )
    result = await request.app.state.alarm_service.create_rule(rule)
    return ApiResponse(data=result)


@router.put("/rules/{rule_id}", response_model=ApiResponse)
async def update_rule(rule_id: int, req: RuleInput, request: Request):
    rule = AlarmRule(
        name=req.name, category=req.category, level=req.level,
        condition_json=req.condition_json, enabled=req.enabled,
    )
    ok = await request.app.state.alarm_service.update_rule(rule_id, rule)
    if not ok:
        return ApiResponse(code=3002, message="Rule not found")
    return ApiResponse(data={"id": rule_id})


@router.delete("/rules/{rule_id}", response_model=ApiResponse)
async def delete_rule(rule_id: int, request: Request):
    ok = await request.app.state.alarm_service.delete_rule(rule_id)
    if not ok:
        return ApiResponse(code=3002, message="Rule not found")
    return ApiResponse(data={"deleted": rule_id})

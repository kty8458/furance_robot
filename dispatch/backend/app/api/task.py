from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from furance_shared.protocol.http_schema import ApiResponse
from app.models.task import TaskTemplate, TaskStep

router = APIRouter(prefix="/api/v1/dispatch/tasks", tags=["tasks"])


class TaskTemplateInput(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    steps: list[dict] = []


class TaskTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict] | None = None


@router.get("", response_model=ApiResponse)
async def list_templates(request: Request):
    templates = await request.app.state.task_editor.list_all()
    return ApiResponse(data=templates)


@router.get("/{template_id}", response_model=ApiResponse)
async def get_template(template_id: str, request: Request):
    template = await request.app.state.task_editor.get(template_id)
    if not template:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    return ApiResponse(data=template)


@router.post("", response_model=ApiResponse)
async def create_template(req: TaskTemplateInput, request: Request):
    existing = await request.app.state.task_editor.get(req.id)
    if existing:
        return ApiResponse(code=3001, message=f"Template {req.id} already exists")
    template = TaskTemplate(
        id=req.id, name=req.name, description=req.description,
        steps=[TaskStep(**s) for s in req.steps],
    )
    result = await request.app.state.task_editor.create(template)
    return ApiResponse(data=result)


@router.put("/{template_id}", response_model=ApiResponse)
async def update_template(template_id: str, req: TaskTemplateUpdate, request: Request):
    existing = await request.app.state.task_editor.get(template_id)
    if not existing:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    import json
    template = TaskTemplate(
        id=template_id,
        name=req.name or existing["name"],
        description=req.description or existing.get("description", ""),
        steps=[TaskStep(**s) for s in req.steps] if req.steps else [TaskStep(**s) for s in json.loads(existing.get("steps_json", "[]"))],
        version=existing.get("version", 1),
    )
    result = await request.app.state.task_editor.update(template)
    return ApiResponse(data=result)


@router.delete("/{template_id}", response_model=ApiResponse)
async def delete_template(template_id: str, request: Request):
    deleted = await request.app.state.task_editor.delete(template_id)
    if not deleted:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    return ApiResponse(data={"deleted": template_id})

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from furance_shared.models.workflow import (
    Workflow,
    WorkflowExecuteRequest,
    WorkflowExecuteResponse,
    StepResult,
    MoveStepConfig,
    UpperLimbStepConfig,
    UpperBodyStepConfig,
    GripperStepConfig,
    VisionStepConfig,
    SleepStepConfig,
)
from furance_shared.models.command import GripperCommand
from furance_shared.utils.errors import BusinessError, ErrorCode

logger = logging.getLogger(__name__)

# Maximum time to wait for navigation task completion (5 minutes = 300 polls at 1s)
NAV_POLL_TIMEOUT = 300
NAV_POLL_INTERVAL = 1.0


class WorkflowService:
    def __init__(
        self,
        ros2_client=None,
        moveit_client=None,
        upper_body_client=None,
        chassis_client=None,
        arm_service=None,
        workflow_dir: str = "data/workflows",
        arm_enable_client=None,
        status_service=None,
    ):
        self._ros2 = ros2_client
        self._moveit = moveit_client
        self._upper_body = upper_body_client
        self._chassis = chassis_client
        self._arm_service = arm_service
        self._workflow_dir = Path(workflow_dir)
        self._arm_enable = arm_enable_client
        self._status_service = status_service
        self._active_executions: dict[str, asyncio.Event] = {}

    # -- CRUD --

    def _robot_dir(self, robot_id: str) -> Path:
        return self._workflow_dir / robot_id

    def _file_path(self, robot_id: str, name: str) -> Path:
        return self._robot_dir(robot_id) / f"{name}.json"

    def list_workflows(self, robot_id: str) -> list[dict]:
        robot_dir = self._robot_dir(robot_id)
        if not robot_dir.is_dir():
            return []
        result = []
        for f in sorted(robot_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                result.append({
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "step_count": len(data.get("steps", [])),
                    "version": data.get("version", 1),
                })
            except Exception:
                result.append({
                    "name": f.stem,
                    "description": "",
                    "step_count": 0,
                    "version": 1,
                })
        return result

    def get_workflow(self, robot_id: str, name: str) -> Workflow:
        file_path = self._file_path(robot_id, name)
        if not file_path.exists():
            raise BusinessError(
                message=f"Workflow '{name}' not found",
                code=ErrorCode.WORKFLOW_NOT_FOUND,
            )
        return Workflow(**json.loads(file_path.read_text()))

    def save_workflow(self, robot_id: str, workflow: Workflow, overwrite: bool = False) -> None:
        robot_dir = self._robot_dir(robot_id)
        robot_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._file_path(robot_id, workflow.name)
        if file_path.exists() and not overwrite:
            raise BusinessError(
                message=f"Workflow '{workflow.name}' already exists",
                code=ErrorCode.WORKFLOW_NAME_EXISTS,
            )
        file_path.write_text(json.dumps(workflow.model_dump(), indent=2, ensure_ascii=False))

    def delete_workflow(self, robot_id: str, name: str) -> None:
        file_path = self._file_path(robot_id, name)
        if file_path.exists():
            file_path.unlink()

    # -- Async execution engine (with cancellation) --

    def start_execution(self, robot_id: str, name: str, execute_req: WorkflowExecuteRequest) -> str:
        """Start workflow execution as a background task.

        Returns execution_id (UUID string) for status tracking and cancellation.
        """
        workflow = self.get_workflow(robot_id, name)
        execution_id = str(uuid.uuid4())
        cancel_event = asyncio.Event()
        self._active_executions[execution_id] = cancel_event
        asyncio.create_task(self._run_workflow(execution_id, robot_id, workflow, execute_req, cancel_event))
        return execution_id

    async def _run_workflow(
        self,
        execution_id: str,
        robot_id: str,
        workflow: Workflow,
        execute_req: WorkflowExecuteRequest,
        cancel_event: asyncio.Event,
    ) -> None:
        try:
            nav_lookup = {np.step_id: np for np in execute_req.nav_params}
            context: dict[str, dict] = {}
            step_results: list[StepResult] = []

            for i, step in enumerate(workflow.steps):
                if cancel_event.is_set():
                    logger.info("Workflow '%s' execution '%s' cancelled at step %d/%d",
                                workflow.name, execution_id, i + 1, len(workflow.steps))
                    break

                logger.info("Workflow '%s' step %d/%d: %s (%s)",
                            workflow.name, i + 1, len(workflow.steps), step.label, step.type)

                self._push_step(robot_id, {
                    "execution_id": execution_id,
                    "workflow_name": workflow.name,
                    "step_index": i,
                    "step_label": step.label,
                    "step_type": step.type,
                    "status": "running",
                })

                try:
                    result = await self._dispatch_step(step, nav_lookup, context, robot_id)
                    step_results.append(result)

                    self._push_step(robot_id, {
                        "execution_id": execution_id,
                        "workflow_name": workflow.name,
                        "step_index": i,
                        "step_label": step.label,
                        "step_type": step.type,
                        "status": "completed" if result.success else "failed",
                        "message": result.message,
                    })
                except Exception as exc:
                    logger.exception("Workflow step '%s' error", step.label)
                    step_results.append(StepResult(step_id=step.id, success=False, message=str(exc)))
                    self._push_step(robot_id, {
                        "execution_id": execution_id,
                        "workflow_name": workflow.name,
                        "step_index": i,
                        "step_label": step.label,
                        "step_type": step.type,
                        "status": "failed",
                        "message": str(exc),
                    })
        finally:
            self._active_executions.pop(execution_id, None)

    def cancel_workflow(self) -> bool:
        """Cancel all active workflow executions.

        Returns True if any executions were cancelled.
        """
        if not self._active_executions:
            return False

        cancelled = False
        for cancel_event in self._active_executions.values():
            cancel_event.set()
            cancelled = True

        if self._chassis is not None:
            try:
                asyncio.create_task(self._chassis.stop_task())
            except Exception:
                logger.exception("Failed to stop chassis task during workflow cancellation")

        if self._arm_enable is not None:
            try:
                self._arm_enable.enable(False)
            except Exception:
                logger.exception("Failed to disable arm during workflow cancellation")
            try:
                self._arm_enable.clear_error()
            except Exception:
                logger.exception("Failed to clear arm error during workflow cancellation")

        return cancelled

    def get_execution_status(self, execution_id: str) -> dict:
        """Return execution status for a given execution_id.

        Returns dict with 'active' bool and 'execution_id' str.
        """
        active = execution_id in self._active_executions
        return {
            "execution_id": execution_id,
            "active": active,
        }

    def _push_step(self, robot_id: str, payload: dict) -> None:
        """Push a workflow step status update via status_service if available."""
        if self._status_service is not None:
            try:
                self._status_service.push_workflow_step(robot_id, payload)
            except Exception:
                logger.exception("Failed to push workflow step status")

    # -- Execution engine (legacy, synchronous-style) --

    async def execute_workflow(
        self, robot_id: str, name: str, execute_req: WorkflowExecuteRequest
    ) -> WorkflowExecuteResponse:
        workflow = self.get_workflow(robot_id, name)
        nav_lookup = {np.step_id: np for np in execute_req.nav_params}
        context: dict[str, dict] = {}
        step_results: list[StepResult] = []

        for i, step in enumerate(workflow.steps):
            logger.info("Workflow '%s' step %d/%d: %s (%s)", name, i + 1, len(workflow.steps), step.label, step.type)
            try:
                result = await self._dispatch_step(step, nav_lookup, context, robot_id)
                step_results.append(result)
                if not result.success:
                    return WorkflowExecuteResponse(
                        success=False,
                        message=f"Step '{step.label}' failed: {result.message}",
                        step_results=step_results,
                        error_step_id=step.id,
                    )
            except Exception as exc:
                logger.exception("Workflow step '%s' error", step.label)
                step_results.append(StepResult(step_id=step.id, success=False, message=str(exc)))
                return WorkflowExecuteResponse(
                    success=False,
                    message=f"Step '{step.label}' error: {exc}",
                    step_results=step_results,
                    error_step_id=step.id,
                )

        return WorkflowExecuteResponse(
            success=True,
            message="Workflow completed",
            step_results=step_results,
        )

    async def _dispatch_step(self, step, nav_lookup, context, robot_id) -> StepResult:
        handlers = {
            "move": self._execute_move,
            "upper_limb": self._execute_upper_limb,
            "upper_body": self._execute_upper_body,
            "gripper": self._execute_gripper,
            "vision": self._execute_vision,
            "sleep": self._execute_sleep,
        }
        handler = handlers.get(step.type)
        if handler is None:
            return StepResult(step_id=step.id, success=False, message=f"Unknown step type: {step.type}")
        return await handler(step, nav_lookup, context, robot_id)

    async def _execute_move(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._chassis is None:
            return StepResult(step_id=step.id, success=False, message="Chassis client not available")

        nav = nav_lookup.get(step.id)
        if nav is None:
            return StepResult(step_id=step.id, success=False, message="Navigation params not provided for this step")

        config = MoveStepConfig(**step.config)
        task_body = {
            "map_name": nav.map_name,
            "loop": False,
            "tasks": [{
                "name": nav.path_type,
                "start_param": {
                    "map_name": nav.map_name,
                    "position_name": nav.point_name or "",
                    "path_name": nav.path_name or "",
                },
            }],
        }

        start_res = await self._chassis.start_task(task_body)
        if not start_res.get("successed", start_res.get("success", False)):
            return StepResult(step_id=step.id, success=False, message=start_res.get("msg", "Navigation start failed"))

        for _ in range(NAV_POLL_TIMEOUT):
            await asyncio.sleep(NAV_POLL_INTERVAL)
            try:
                status = await self._chassis.is_task_finished()
                if status.get("data", {}).get("is_finished", False):
                    return StepResult(step_id=step.id, success=True, message="Navigation completed")
            except Exception:
                pass

        return StepResult(step_id=step.id, success=False, message="Navigation timed out")

    async def _execute_upper_limb(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._moveit is None:
            return StepResult(step_id=step.id, success=False, message="MoveIt client not available")

        config = UpperLimbStepConfig(**step.config)

        if config.mode == "preset":
            if not config.preset_name or self._arm_service is None:
                return StepResult(step_id=step.id, success=False, message="Preset name required")
            presets = self._arm_service.list_teach(robot_id)
            preset = next((p for p in presets if p.name == config.preset_name and p.arm.value == config.arm), None)
            if preset is None:
                return StepResult(step_id=step.id, success=False, message=f"Preset '{config.preset_name}' not found")

            method = config.method
            if method == "moveJ":
                result = await self._moveit.move_j(config.arm, preset.joint_angles)
            elif method == "moveL":
                result = await self._moveit.move_l(config.arm, [preset.end_effector.model_dump()])
            else:  # movep
                to_frame = f"ARM-{'L' if config.arm == 'left' else 'R'}-J7_Link"
                result = await self._moveit.move_p(
                    config.arm, preset.end_effector.model_dump(),
                    to_frame, preset.coordinate_frame, "ompl",
                )
        else:  # pose mode
            resolved = self._resolve_variables(config.position or {}, context)
            to_frame = f"ARM-{'L' if config.arm == 'left' else 'R'}-J7_Link"
            result = await self._moveit.move_p(
                config.arm, resolved,
                to_frame, config.reference_frame or "base_link", "ompl",
            )

        if result.get("success") is False:
            return StepResult(step_id=step.id, success=False, message=result.get("message", "Upper limb move failed"))
        return StepResult(step_id=step.id, success=True, message="Upper limb move completed")

    async def _execute_upper_body(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._upper_body is None:
            return StepResult(step_id=step.id, success=False, message="Upper body client not available")

        config = UpperBodyStepConfig(**step.config)
        if config.waist_angle is not None:
            r = await self._upper_body.waist_control(config.waist_angle, config.waist_speed)
            if r.get("success") is False:
                return StepResult(step_id=step.id, success=False, message=r.get("message", "Waist control failed"))
        if config.ascend_pos is not None:
            r = await self._upper_body.ascend_control(config.ascend_pos, config.ascend_speed)
            if r.get("success") is False:
                return StepResult(step_id=step.id, success=False, message=r.get("message", "Ascend control failed"))
        if config.head_angle is not None:
            r = await self._upper_body.head_control(config.head_angle, config.head_speed)
            if r.get("success") is False:
                return StepResult(step_id=step.id, success=False, message=r.get("message", "Head control failed"))
        return StepResult(step_id=step.id, success=True, message="Upper body control completed")

    async def _execute_gripper(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._ros2 is None:
            return StepResult(step_id=step.id, success=False, message="ROS2 client not available")

        config = GripperStepConfig(**step.config)
        cmd = GripperCommand(arm=config.arm, action=config.action, force=config.force)
        result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
        if result.get("success") is False:
            return StepResult(step_id=step.id, success=False, message=result.get("message", "Gripper command failed"))
        return StepResult(step_id=step.id, success=True, message=f"Gripper {config.action} completed")

    async def _execute_vision(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._ros2 is None:
            return StepResult(step_id=step.id, success=False, message="ROS2 client not available")

        config = VisionStepConfig(**step.config)
        result = await self._ros2.call_service("/vision_detect", {"scene": config.scene, "camera_id": config.camera_id})
        if result.get("success") is False:
            return StepResult(step_id=step.id, success=False, message=result.get("message", "Vision detection failed"))

        data = result.get("data", {})
        grasp_pose = data.get("grasp_pose") or data
        context[step.id] = {"grasp_pose": grasp_pose}
        return StepResult(step_id=step.id, success=True, message="Vision detection completed", data={"grasp_pose": grasp_pose})

    async def _execute_sleep(self, step, nav_lookup, context, robot_id) -> StepResult:
        config = SleepStepConfig(**step.config)
        await asyncio.sleep(config.duration)
        return StepResult(step_id=step.id, success=True, message=f"Slept {config.duration}s")

    @staticmethod
    def _resolve_variables(value: Any, context: dict) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            parts = value[1:].split(".")
            current: Any = context
            for key in parts:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    return value
            return current
        elif isinstance(value, dict):
            return {k: WorkflowService._resolve_variables(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [WorkflowService._resolve_variables(v, context) for v in value]
        return value

import json
from pathlib import Path
from furance_shared.models.robot import ArmSide
from furance_shared.utils.errors import BusinessError, ErrorCode
from app.models.teach import TeachPreset, TeachPresetSummary
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient
from app.ros2.moveit_client import MoveItServiceClientBase
from furance_shared.models.command import ArmMoveCommand, TeachSaveCommand, TeachExecCommand
from furance_shared.protocol.http_schema import ApiResponse


class ArmService:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None,
                 moveit_client: MoveItServiceClientBase | None = None,
                 teach_dir: str = "data/teach"):
        self._ros2 = ros2_client or MockRos2ServiceClient()
        self._moveit = moveit_client
        self._teach_dir = Path(teach_dir)

    async def arm_move(self, robot_id: str, cmd: ArmMoveCommand) -> ApiResponse:
        if cmd.method.value == "movep" and self._moveit:
            to_frame = f"ARM-{'L' if cmd.arm.value == 'left' else 'R'}-J7_Link"
            result = await self._moveit.move_p(
                lor=cmd.arm.value,
                target_pose=cmd.position or {},
                to_frame=to_frame,
                reference_frame=cmd.coordinate,
                planner="ompl",
            )
            if result.get("success") is False:
                return ApiResponse(code=1001, message=result.get("message", "MoveP 失败"))
            return ApiResponse(data=result)

        if cmd.method.value == "moveL" and self._moveit:
            result = await self._moveit.move_l(
                lor=cmd.arm.value,
                waypoints=[cmd.position] if cmd.position else [],
            )
            if result.get("success") is False:
                return ApiResponse(code=1001, message=result.get("message", "MoveL 失败"))
            return ApiResponse(data=result)

        # Fallback to GenericCommand for moveJ and other methods
        result = await self._ros2.call_service("/ArmMoveCommand", cmd.model_dump())
        if result.get("success") is False:
            return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
        return ApiResponse(data=result)

    def save_teach(self, robot_id: str, preset: TeachPreset, overwrite: bool = False) -> None:
        robot_dir = self._teach_dir / robot_id
        robot_dir.mkdir(parents=True, exist_ok=True)
        file_path = robot_dir / "presets.json"
        presets = self._load_presets(file_path)
        key = f"{preset.arm.value}_{preset.name}"
        if key in presets and not overwrite:
            raise BusinessError(
                message=f"Teach preset '{preset.name}' already exists for {preset.arm}",
                code=ErrorCode.TEACH_NAME_EXISTS,
            )
        presets[key] = preset.model_dump()
        file_path.write_text(json.dumps(presets, indent=2))

    def list_teach(self, robot_id: str) -> list[TeachPreset]:
        robot_dir = self._teach_dir / robot_id
        file_path = robot_dir / "presets.json"
        if not file_path.exists():
            return []
        presets = self._load_presets(file_path)
        result = []
        for v in presets.values():
            try:
                result.append(TeachPreset(**v))
            except Exception:
                continue
        return result

    def delete_teach(self, robot_id: str, name: str) -> None:
        robot_dir = self._teach_dir / robot_id
        file_path = robot_dir / "presets.json"
        if not file_path.exists():
            return
        presets = self._load_presets(file_path)
        keys_to_delete = [k for k, v in presets.items() if v["name"] == name]
        for k in keys_to_delete:
            del presets[k]
        file_path.write_text(json.dumps(presets, indent=2))

    async def exec_teach(self, robot_id: str, cmd: TeachExecCommand) -> ApiResponse:
        robot_dir = self._teach_dir / robot_id
        file_path = robot_dir / "presets.json"
        presets = self._load_presets(file_path)
        key = f"{cmd.arm.value}_{cmd.name}"
        if key not in presets:
            raise BusinessError(
                message=f"Teach preset '{cmd.name}' not found for {cmd.arm}",
                code=ErrorCode.TEACH_NAME_NOT_FOUND,
            )
        preset_data = presets[key]
        move_cmd = ArmMoveCommand(
            arm=cmd.arm,
            method=cmd.method,
            joint_angles=preset_data.get("joint_angles"),
            position=preset_data.get("end_effector"),
            coordinate=preset_data.get("coordinate_frame", "base_link"),
        )
        result = await self._ros2.call_service("/ArmMoveCommand", move_cmd.model_dump())
        if result.get("success") is False:
            return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
        return ApiResponse(data=result)

    def _load_presets(self, file_path: Path) -> dict:
        if not file_path.exists():
            return {}
        return json.loads(file_path.read_text())

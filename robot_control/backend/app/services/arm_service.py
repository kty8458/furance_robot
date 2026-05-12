import json
from pathlib import Path
from furance_shared.models.robot import ArmSide
from furance_shared.utils.errors import BusinessError, ErrorCode
from app.models.teach import TeachPreset, TeachPresetSummary
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient
from furance_shared.models.command import ArmMoveCommand, TeachSaveCommand, TeachExecCommand
from furance_shared.protocol.http_schema import ApiResponse


class ArmService:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None, teach_dir: str = "data/teach"):
        self._ros2 = ros2_client or MockRos2ServiceClient()
        self._teach_dir = Path(teach_dir)

    async def arm_move(self, robot_id: str, cmd: ArmMoveCommand) -> ApiResponse:
        result = await self._ros2.call_service("/ArmMoveCommand", cmd.model_dump())
        if result.get("success") is False:
            return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
        return ApiResponse(data=result)

    def save_teach(self, robot_id: str, preset: TeachPreset) -> None:
        robot_dir = self._teach_dir / robot_id
        robot_dir.mkdir(parents=True, exist_ok=True)
        file_path = robot_dir / "presets.json"
        presets = self._load_presets(file_path)
        key = f"{preset.arm.value}_{preset.name}"
        if key in presets:
            raise BusinessError(
                message=f"Teach preset '{preset.name}' already exists for {preset.arm}",
                code=ErrorCode.TEACH_NAME_EXISTS,
            )
        presets[key] = preset.model_dump()
        file_path.write_text(json.dumps(presets, indent=2))

    def list_teach(self, robot_id: str) -> list[TeachPresetSummary]:
        robot_dir = self._teach_dir / robot_id
        file_path = robot_dir / "presets.json"
        if not file_path.exists():
            return []
        presets = self._load_presets(file_path)
        return [
            TeachPresetSummary(arm=v["arm"], name=v["name"])
            for v in presets.values()
        ]

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
        result = await self._ros2.call_service("/ArmTeachExec", cmd.model_dump())
        if result.get("success") is False:
            return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
        return ApiResponse(data=result)

    def _load_presets(self, file_path: Path) -> dict:
        if not file_path.exists():
            return {}
        return json.loads(file_path.read_text())

import json
from pathlib import Path
from furance_shared.models.robot import ArmSide
from furance_shared.utils.errors import BusinessError, ErrorCode
from app.models.teach import TeachPreset, TeachPresetSummary
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient
from app.ros2.moveit_client import MoveItServiceClientBase
from furance_shared.models.command import ArmMoveCommand, TeachSaveCommand, TeachExecCommand, ArmMoveMethod
from furance_shared.protocol.http_schema import ApiResponse


class ArmService:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None,
                 moveit_client: MoveItServiceClientBase | None = None,
                 teach_dir: str = "data/teach"):
        self._ros2 = ros2_client or MockRos2ServiceClient()
        self._moveit = moveit_client
        self._teach_dir = Path(teach_dir)

    async def arm_move(self, robot_id: str, cmd: ArmMoveCommand) -> ApiResponse:
        import logging
        logging.getLogger(__name__).info(
            "EVENT arm_move arm=%s method=%s coordinate=%s",
            cmd.arm.value, cmd.method.value, cmd.coordinate,
        )

        arm = cmd.arm.value

        # Dual-arm moveJ: send left+right together to both_move_group
        if arm == "both" and cmd.method.value == "moveJ" and self._moveit:
            left = cmd.joint_angles or []
            right = cmd.joint_angles_right or []
            if len(left) != 7 or len(right) != 7:
                return ApiResponse(code=3001, message="moveJ both requires 7+7 joint angles")
            result = await self._moveit.move_j_both(left, right)
            if result.get("success") is False:
                return ApiResponse(code=1001, message=result.get("message", "双臂 MoveJ 失败"))
            return ApiResponse(data=result)

        if arm == "both" and cmd.method.value in ("movep", "moveL"):
            return ApiResponse(code=3001, message="双臂模式目前仅支持 moveJ")

        if cmd.method.value == "movep" and self._moveit:
            to_frame = f"ARM-{'L' if arm == 'left' else 'R'}-J7_Link"
            result = await self._moveit.move_p(
                lor=arm,
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
                lor=arm,
                waypoints=[cmd.position] if cmd.position else [],
            )
            if result.get("success") is False:
                return ApiResponse(code=1001, message=result.get("message", "MoveL 失败"))
            return ApiResponse(data=result)

        if cmd.method.value == "moveJ" and self._moveit:
            result = await self._moveit.move_j(
                lor=arm,
                joint_positions=cmd.joint_angles or [],
            )
            if result.get("success") is False:
                return ApiResponse(code=1001, message=result.get("message", "MoveJ 失败"))
            return ApiResponse(data=result)

        # Fallback to legacy ROS2 service (used in mock mode without moveit_client)
        result = await self._ros2.call_service("/ArmMoveCommand", cmd.model_dump())
        if result.get("success") is False:
            return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
        return ApiResponse(data=result)

    def _teach_file_path(self, robot_id: str, workflow_name: str = None) -> Path:
        """返回示教点文件路径。workflow_name=None 为全局, 否则为工作流级。"""
        if workflow_name:
            wf_dir = self._teach_dir / robot_id / "workflows" / workflow_name
            wf_dir.mkdir(parents=True, exist_ok=True)
            return wf_dir / "teach_presets.json"
        else:
            robot_dir = self._teach_dir / robot_id
            robot_dir.mkdir(parents=True, exist_ok=True)
            return robot_dir / "presets.json"

    def save_teach(self, robot_id: str, preset: TeachPreset, overwrite: bool = False,
                   workflow_name: str = None) -> None:
        file_path = self._teach_file_path(robot_id, workflow_name)
        presets = self._load_presets(file_path)
        key = f"{preset.arm.value}_{preset.name}"
        if key in presets and not overwrite:
            raise BusinessError(
                message=f"Teach preset '{preset.name}' already exists for {preset.arm}",
                code=ErrorCode.TEACH_NAME_EXISTS,
            )
        presets[key] = preset.model_dump()
        file_path.write_text(json.dumps(presets, indent=2))

    def list_teach(self, robot_id: str, workflow_name: str = None) -> list[TeachPreset]:
        """列出示教点。workflow_name=None 只返回全局; 否则返回全局+工作流级合并。"""
        result = []
        # 全局
        global_path = self._teach_file_path(robot_id, None)
        if global_path.exists():
            presets = self._load_presets(global_path)
            for v in presets.values():
                try:
                    p = TeachPreset(**v)
                    result.append(p)
                except Exception:
                    continue
        # 工作流级 (合并到全局之上)
        if workflow_name:
            wf_path = self._teach_file_path(robot_id, workflow_name)
            if wf_path.exists():
                wf_presets = self._load_presets(wf_path)
                for v in wf_presets.values():
                    try:
                        p = TeachPreset(**v)
                        result.append(p)
                    except Exception:
                        continue
        return result

    def delete_teach(self, robot_id: str, name: str, workflow_name: str = None) -> None:
        file_path = self._teach_file_path(robot_id, workflow_name)
        if not file_path.exists():
            return
        presets = self._load_presets(file_path)
        keys_to_delete = [k for k, v in presets.items() if v["name"] == name]
        for k in keys_to_delete:
            del presets[k]
        file_path.write_text(json.dumps(presets, indent=2))

    async def exec_teach(self, robot_id: str, cmd: TeachExecCommand, workflow_name: str = None) -> ApiResponse:
        # 先从工作流级找, 没有再从全局找
        presets = {}
        if workflow_name:
            wf_path = self._teach_file_path(robot_id, workflow_name)
            if wf_path.exists():
                presets = self._load_presets(wf_path)
        key = f"{cmd.arm.value}_{cmd.name}"
        if key not in presets:
            # fallback 到全局
            global_path = self._teach_file_path(robot_id, None)
            if global_path.exists():
                presets = self._load_presets(global_path)
        if key not in presets:
            raise BusinessError(
                message=f"Teach preset '{cmd.name}' not found for {cmd.arm}",
                code=ErrorCode.TEACH_NAME_NOT_FOUND,
            )
        preset_data = presets[key]
        stored_method = preset_data.get("method", "moveJ")
        method = cmd.method.value if cmd.method else stored_method

        joint_angles = preset_data.get("joint_angles", [])
        joint_angles_right = preset_data.get("joint_angles_right")

        # Both-arm preset: split 14 joint_angles into left(7) + right(7)
        if cmd.arm.value == "both" and len(joint_angles) == 14:
            joint_angles_right = joint_angles[7:]
            joint_angles = joint_angles[:7]

        move_cmd = ArmMoveCommand(
            arm=cmd.arm,
            method=method,
            joint_angles=joint_angles,
            joint_angles_right=joint_angles_right,
            position=preset_data.get("end_effector"),
            coordinate=preset_data.get("coordinate_frame", "base_link"),
        )
        return await self.arm_move(robot_id, move_cmd)

    def compose_teach(self, robot_id: str, left_name: str, right_name: str, composed_name: str,
                      overwrite: bool = False, workflow_name: str = None) -> TeachPreset:
        """Combine two single-arm moveJ presets into one dual-arm preset."""
        # 合并全局+工作流级示教点
        presets = {}
        global_path = self._teach_file_path(robot_id, None)
        if global_path.exists():
            presets = self._load_presets(global_path)
        if workflow_name:
            wf_path = self._teach_file_path(robot_id, workflow_name)
            if wf_path.exists():
                presets.update(self._load_presets(wf_path))

        left_key = f"left_{left_name}"
        right_key = f"right_{right_name}"

        if left_key not in presets:
            raise BusinessError(
                message=f"Left preset '{left_name}' not found",
                code=ErrorCode.TEACH_NAME_NOT_FOUND,
            )
        if right_key not in presets:
            raise BusinessError(
                message=f"Right preset '{right_name}' not found",
                code=ErrorCode.TEACH_NAME_NOT_FOUND,
            )

        left_data = presets[left_key]
        right_data = presets[right_key]

        if left_data.get("method", "moveJ") != "moveJ" or right_data.get("method", "moveJ") != "moveJ":
            raise BusinessError(
                message="Compose only supports moveJ presets",
                code=ErrorCode.TEACH_NAME_EXISTS,
            )

        composed_key = f"both_{composed_name}"
        if composed_key in presets and not overwrite:
            raise BusinessError(
                message=f"Both-arm preset '{composed_name}' already exists",
                code=ErrorCode.TEACH_NAME_EXISTS,
            )

        preset = TeachPreset(
            arm="both",
            name=composed_name,
            joint_angles=left_data.get("joint_angles", [0] * 7) + right_data.get("joint_angles", [0] * 7),
            joint_angles_right=right_data.get("joint_angles", [0] * 7),
            method="moveJ",
            coordinate_frame=left_data.get("coordinate_frame", "base_link"),
        )
        presets[composed_key] = preset.model_dump()
        save_path = self._teach_file_path(robot_id, workflow_name)
        # 如果是工作流级, 先读已有的工作流级 presets 再追加
        if workflow_name and save_path.exists():
            existing = self._load_presets(save_path)
            existing[composed_key] = preset.model_dump()
            save_path.write_text(json.dumps(existing, indent=2))
        else:
            save_path.write_text(json.dumps(presets, indent=2))
        return preset

    def _load_presets(self, file_path: Path) -> dict:
        if not file_path.exists():
            return {}
        return json.loads(file_path.read_text())

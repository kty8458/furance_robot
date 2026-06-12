import asyncio
import time
from fastapi import WebSocket
from furance_shared.protocol.ws_frames import (
    StatusFrame, ErrorFrame, WorkflowStepFrame, AlarmFrame, WsFrameType,
)
from furance_shared.models.robot import Position, GripperInfo, GripperState, ArmState

# Timeouts in seconds: if a source hasn't updated within this window,
# it is marked as "disconnected" in source_status.
SOURCE_TIMEOUTS = {
    "chassis": 5.0,     # chassis poller runs every 1s
    "ros2_status": 5.0, # /robot_status runs at 1Hz
    "ros2_motor": 5.0,  # /motor_feedback runs at 1Hz
    "ros2_joint": 5.0,  # joint_state_listener runs at 2Hz
}

DEFAULT_ROBOT_ID = "robot_001"


class StatusService:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._latest: dict[str, dict] = {}
        self._ros2_cache: dict[str, dict] = {}
        # Track when each source last contributed fresh data (monotonic seconds)
        self._source_last: dict[str, dict[str, float]] = {}

    def add_connection(self, ws: WebSocket):
        self._connections.append(ws)

    def remove_connection(self, ws: WebSocket):
        self._connections.remove(ws)

    def get_latest(self, robot_id: str) -> dict | None:
        return self._latest.get(robot_id)

    # ---- ROS2 cache (write-only from listeners) ----

    async def update_ros2_cache(self, robot_id: str, data: dict):
        """Store ROS2-originated data (arm, gripper, enabled, error_code).

        Called by topic_listener, joint_state_listener, and motor_feedback_listener.
        Also marks the appropriate source as fresh and triggers a push if
        chassis data is already cached.
        """
        cache = self._ros2_cache.get(robot_id) or {}
        cache.update(data)
        self._ros2_cache[robot_id] = cache

    def get_ros2_cache(self, robot_id: str) -> dict:
        return self._ros2_cache.get(robot_id) or {}

    # ---- Source freshness tracking ----

    def mark_source_fresh(self, robot_id: str, source: str):
        """Record that *source* just produced fresh data."""
        if robot_id not in self._source_last:
            self._source_last[robot_id] = {}
        self._source_last[robot_id][source] = time.monotonic()

    def _build_source_status(self, robot_id: str, now: float | None = None) -> dict[str, bool]:
        """Return {source: connected_bool} for all known sources."""
        if now is None:
            now = time.monotonic()
        last = self._source_last.get(robot_id, {})
        result = {}
        for source, timeout in SOURCE_TIMEOUTS.items():
            t = last.get(source, 0.0)
            result[source] = (now - t) < timeout
        return result

    # ---- Independent push from each source ----

    async def push_chassis_status(self, robot_id: str, chassis_data: dict):
        """Push a snapshot merging fresh chassis data with cached ROS2 data."""
        self.mark_source_fresh(robot_id, "chassis")
        merged = self._merge(robot_id, chassis_data)
        await self._do_push(robot_id, merged)

    async def push_ros2_snapshot(self, robot_id: str):
        """Push a snapshot using only cached ROS2 data (chassis may be stale).

        Called by ROS2 listeners when they receive fresh data, so arm/motor/gripper
        updates reach the frontend even when the chassis is unreachable.
        """
        merged = self._merge(robot_id, None)
        await self._do_push(robot_id, merged)

    async def _do_push(self, robot_id: str, status_data: dict):
        """Broadcast the merged status and cache it as latest."""
        self._latest[robot_id] = status_data
        frame = StatusFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload=status_data,
        )
        await self._broadcast(frame.model_dump())

    # ---- Merge logic (extracted from old ChassisStatusPoller) ----

    def _merge(self, robot_id: str, chassis_data: dict | None) -> dict:
        """Merge chassis + ROS2 cache into a unified status dict.

        When *chassis_data* is None the chassis fields are pulled from the
        previously-cached latest snapshot (or zeroed out on first call).
        """
        ros2 = self.get_ros2_cache(robot_id)

        # --- chassis-derived fields ---
        if chassis_data is not None:
            position = {
                "x": float(chassis_data.get("world_x", 0.0)),
                "y": float(chassis_data.get("world_y", 0.0)),
                "theta": float(chassis_data.get("theta", 0.0)),
            }
            battery = int(chassis_data.get("battery_percentage", 0))
            charging = bool(chassis_data.get("charge", 0))
            current_map = chassis_data.get("map_name", "")
        else:
            # Reuse last-known chassis values from the cached latest snapshot
            prev = self._latest.get(robot_id) or {}
            position = prev.get("position", {"x": 0.0, "y": 0.0, "theta": 0.0})
            battery = prev.get("battery", 0)
            charging = prev.get("charging", False)
            current_map = prev.get("current_map", "")

        # --- ROS2-derived fields ---
        # 上身连接状态: motor 有数据则视为在线
        motor_data = ros2.get("motor", {})
        upper_body_connected = bool(motor_data)

        merged = {
            "position": position,
            "current_map": current_map,
            "battery": battery,
            "charging": charging,
            "lift_height": ros2.get("lift_height", 0.0),
            "gripper": ros2.get("gripper", {
                "left": {"state": "open", "force": 0.0},
                "right": {"state": "open", "force": 0.0},
            }),
            "enabled": ros2.get("enabled", False),
            "error_code": ros2.get("error_code", 0),
            "task_status": ros2.get("task_status", "idle"),
            "arm": ros2.get("arm", {}),
            "motor": motor_data,
            "source_status": self._build_source_status(robot_id),
            # 底盘新增字段
            "chassis_error": int(chassis_data.get("error", 0)) if chassis_data else 0,
            "chassis_state": int(chassis_data.get("current_working", 0)) if chassis_data else 0,
            "upper_body_connected": upper_body_connected,
        }
        return merged

    # ---- Legacy: still supported for existing callers ----

    async def push_status(self, robot_id: str, status_data: dict):
        """Full push — used by ChassisStatusPoller (old path, kept for compat).

        Prefer push_chassis_status() or push_ros2_snapshot() for new code.
        """
        self._latest[robot_id] = status_data
        frame = StatusFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload=status_data,
        )
        await self._broadcast(frame.model_dump())

    # ---- Error / workflow / alarm broadcasts (unchanged) ----

    async def push_error(self, robot_id: str, error_code: int, error_msg: str, source: str):
        frame = ErrorFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload={"error_code": error_code, "error_msg": error_msg, "source": source},
        )
        await self._broadcast(frame.model_dump())

    async def _broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._connections:
                self._connections.remove(ws)

    async def push_workflow_step(self, robot_id: str, payload: dict):
        frame = WorkflowStepFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload=payload,
        )
        await self._broadcast(frame.model_dump())

    async def push_alarm(self, robot_id: str, payload: dict):
        frame = AlarmFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload=payload,
        )
        await self._broadcast(frame.model_dump())

    @property
    def connection_count(self) -> int:
        return len(self._connections)

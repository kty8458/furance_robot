"""Periodic 1-minute heartbeat logger.

Once per minute, reads the latest merged status from StatusService and emits
a single summary line covering chassis (battery/charging/map/position) and
upper-limb (enabled/arm joints/gripper). Lets operators verify "the robot
is still alive" without scrolling through a frame-by-frame stream.
"""
import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.status_service import StatusService

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 60.0
DEFAULT_ROBOT_ID = "robot_001"


class StatusHeartbeat:
    """Background task that logs a one-line status snapshot every minute."""

    def __init__(self, status_service: "StatusService"):
        self._status_service = status_service
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("StatusHeartbeat started (interval=%ds)", int(HEARTBEAT_INTERVAL))

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self):
        while self._running:
            try:
                self._emit()
            except Exception:
                logger.exception("Heartbeat emit failed")
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    def _emit(self):
        snap = self._status_service.get_latest(DEFAULT_ROBOT_ID) or {}
        pos = snap.get("position") or {}
        gripper = snap.get("gripper") or {}
        arm = snap.get("arm") or {}
        motor = snap.get("motor") or {}
        left_joints = (arm.get("left") or {}).get("joint_angles") or []
        right_joints = (arm.get("right") or {}).get("joint_angles") or []

        def _fmt_joints(js):
            if not js:
                return "--"
            return "[" + ",".join(f"{j:.1f}" for j in js[:7]) + "]"

        def _fmt_num(v, suffix="", decimals=1):
            return f"{v:.{decimals}f}{suffix}" if isinstance(v, (int, float)) else "--"

        logger.info(
            "HEARTBEAT chassis battery=%s%% charging=%s map=%s pos=(%.2f,%.2f,%.2f) | "
            "upper enabled=%s error=%s task=%s | "
            "motor head_pan=%s head_tilt=%s lift=%s | "
            "gripper L=%s R=%s | arm L=%s R=%s",
            snap.get("battery", "?"),
            snap.get("charging", "?"),
            snap.get("current_map", ""),
            pos.get("x", 0.0), pos.get("y", 0.0), pos.get("theta", 0.0),
            snap.get("enabled", "?"),
            snap.get("error_code", "?"),
            snap.get("task_status", "?"),
            _fmt_num(motor.get("head_pan_deg"), "°"),
            _fmt_num(motor.get("head_tilt_deg"), "°"),
            _fmt_num(motor.get("lift_height_mm"), "mm", decimals=0),
            (gripper.get("left") or {}).get("state", "?"),
            (gripper.get("right") or {}).get("state", "?"),
            _fmt_joints(left_joints),
            _fmt_joints(right_joints),
        )

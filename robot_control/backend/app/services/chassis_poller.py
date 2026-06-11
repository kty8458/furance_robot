import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.status_service import StatusService
    from app.services.chassis_client import ChassisClient, MockChassisClient

logger = logging.getLogger(__name__)

POLL_INTERVAL = 1.0
DEFAULT_ROBOT_ID = "robot_001"


class ChassisStatusPoller:
    """Polls chassis /real_time_data/robot_hardware_status every 1s.

    On success: merges chassis data (position, battery, charge, map) with
    ROS2 topic data (arm, gripper, enabled, error_code) and pushes via
    StatusService.push_chassis_status().

    On failure: still pushes ROS2-cached data via StatusService.push_ros2_snapshot()
    so the frontend continues to receive arm/motor/gripper updates even when
    the chassis is unreachable. The chassis source is marked as disconnected
    in source_status.
    """

    def __init__(self, chassis_client, status_service: "StatusService"):
        self._chassis = chassis_client
        self._status_service = status_service
        self._task: asyncio.Task | None = None
        self._running = False
        # Track previous values to log only on change
        self._prev_battery: int | None = None
        self._prev_charging: bool | None = None
        self._prev_map: str | None = None
        self._consecutive_failures = 0

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("ChassisStatusPoller started (interval=%ss)", POLL_INTERVAL)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ChassisStatusPoller stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                result = await self._chassis.get_hardware_status()
                if result.get("success"):
                    if self._consecutive_failures > 0:
                        logger.info("EVENT chassis_recovered after %d failures",
                                    self._consecutive_failures)
                        self._consecutive_failures = 0
                    chassis_data = result["data"]
                    self._log_state_changes(chassis_data)
                    await self._status_service.push_chassis_status(
                        DEFAULT_ROBOT_ID, chassis_data,
                    )
                else:
                    self._consecutive_failures += 1
                    if self._consecutive_failures in (1, 5, 30):
                        logger.warning("EVENT chassis_poll_failed (%d consecutive): %s",
                                       self._consecutive_failures, result.get("message"))
                    # Still push ROS2 data so arm/motor/gripper remain live
                    await self._status_service.push_ros2_snapshot(DEFAULT_ROBOT_ID)
            except Exception:
                self._consecutive_failures += 1
                if self._consecutive_failures in (1, 5, 30):
                    logger.exception("EVENT chassis_poll_exception (%d consecutive)",
                                     self._consecutive_failures)
                # Still push ROS2 data so arm/motor/gripper remain live
                await self._status_service.push_ros2_snapshot(DEFAULT_ROBOT_ID)
            await asyncio.sleep(POLL_INTERVAL)

    def _log_state_changes(self, chassis_data: dict):
        """Log notable chassis state transitions (battery, charging, map)."""
        battery = int(chassis_data.get("battery_percentage", 0))
        charging = bool(chassis_data.get("charge", 0))
        current_map = chassis_data.get("map_name", "")

        if self._prev_charging is not None and charging != self._prev_charging:
            logger.info("EVENT chassis_charging_changed from=%s to=%s",
                        self._prev_charging, charging)
        if self._prev_map is not None and current_map != self._prev_map:
            logger.info("EVENT chassis_map_changed from=%s to=%s",
                        self._prev_map, current_map)
        if self._prev_battery is not None:
            for thresh in (50, 30, 20, 10, 5):
                if self._prev_battery > thresh >= battery:
                    logger.warning("EVENT chassis_battery_below threshold=%d current=%d%%",
                                   thresh, battery)
                    break
        self._prev_battery = battery
        self._prev_charging = charging
        self._prev_map = current_map

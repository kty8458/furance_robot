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

    Merges chassis data (position, battery, charge, map) with existing
    ROS2 topic data (arm, gripper, enabled, error_code) from StatusService,
    then pushes the merged snapshot.
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
                    await self._merge_and_push(result["data"])
                else:
                    self._consecutive_failures += 1
                    if self._consecutive_failures in (1, 5, 30):
                        logger.warning("EVENT chassis_poll_failed (%d consecutive): %s",
                                       self._consecutive_failures, result.get("message"))
            except Exception:
                self._consecutive_failures += 1
                if self._consecutive_failures in (1, 5, 30):
                    logger.exception("EVENT chassis_poll_exception (%d consecutive)",
                                     self._consecutive_failures)
            await asyncio.sleep(POLL_INTERVAL)

    async def _merge_and_push(self, chassis_data: dict):
        ros2 = self._status_service.get_ros2_cache(DEFAULT_ROBOT_ID)

        position = {
            "x": float(chassis_data.get("world_x", 0.0)),
            "y": float(chassis_data.get("world_y", 0.0)),
            "theta": float(chassis_data.get("theta", 0.0)),
        }

        battery = int(chassis_data.get("battery_percentage", 0))
        charging = bool(chassis_data.get("charge", 0))
        current_map = chassis_data.get("map_name", "")

        # Log notable state changes (battery thresholds, charge toggle, map change)
        if self._prev_charging is not None and charging != self._prev_charging:
            logger.info("EVENT chassis_charging_changed from=%s to=%s",
                        self._prev_charging, charging)
        if self._prev_map is not None and current_map != self._prev_map:
            logger.info("EVENT chassis_map_changed from=%s to=%s",
                        self._prev_map, current_map)
        if self._prev_battery is not None:
            # log when battery crosses 50/30/20/10/5% threshold
            for thresh in (50, 30, 20, 10, 5):
                if self._prev_battery > thresh >= battery:
                    logger.warning("EVENT chassis_battery_below threshold=%d current=%d%%",
                                   thresh, battery)
                    break
        self._prev_battery = battery
        self._prev_charging = charging
        self._prev_map = current_map

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
            "motor": ros2.get("motor", {}),
        }

        await self._status_service.push_status(DEFAULT_ROBOT_ID, merged)

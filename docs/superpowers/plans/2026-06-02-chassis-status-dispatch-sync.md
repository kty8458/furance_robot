# Chassis Status Polling & Dispatch Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poll chassis `/real_time_data/robot_hardware_status` for position/battery/charge/map in control system, fix dispatch port and workflow proxy to work with real hardware.

**Architecture:** 3 independent tasks — control system adds a 1s polling loop that merges chassis HTTP data with ROS2 topic data before pushing via StatusService; dispatch fixes two config/code bugs blocking real-system connectivity.

**Tech Stack:** Python 3.10+ / asyncio / httpx / FastAPI

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `robot_control/backend/app/services/chassis_poller.py` | Create | Background poller: fetch chassis status, merge with ROS2 data, push via StatusService |
| `robot_control/backend/app/services/chassis_client.py` | Modify | Add `get_hardware_status()` to ChassisClient + MockChassisClient |
| `robot_control/backend/app/main.py` | Modify | Start/stop ChassisStatusPoller in lifespan |
| `dispatch/backend/app/core/config.py` | Modify | Change default port 9001→8000 |
| `dispatch/backend/app/services/robot_proxy.py` | Modify | Remove __init__ pre-population, use lazy DB lookup only |

---

## Task 1: Add `get_hardware_status` to ChassisClient

**Files:**
- Modify: `robot_control/backend/app/services/chassis_client.py`

- [ ] **Step 1: Add method to ChassisClient**

Add after `recharge()` at line 173:

```python
    async def get_hardware_status(self) -> dict[str, Any]:
        """Poll chassis hardware status (position, battery, charge, map)."""
        await self._ensure_token()
        return await self._request("GET", "/real_time_data/robot_hardware_status")
```

- [ ] **Step 2: Add mock method to MockChassisClient**

Add after `recharge()` at line 221:

```python
    async def get_hardware_status(self) -> dict[str, Any]:
        import random
        return {
            "success": True, "message": "ok",
            "data": {
                "world_x": round(random.uniform(-5, 5), 2),
                "world_y": round(random.uniform(-5, 5), 2),
                "theta": round(random.uniform(-3.14, 3.14), 2),
                "battery_percentage": random.randint(30, 95),
                "charge": random.choice([0, 1]),
                "map_name": "workshop_map",
            },
        }
```

- [ ] **Step 3: Commit**

```bash
git add robot_control/backend/app/services/chassis_client.py
git commit -m "feat: add get_hardware_status to ChassisClient and mock"
```

---

## Task 2: Create ChassisStatusPoller

**Files:**
- Create: `robot_control/backend/app/services/chassis_poller.py`

- [ ] **Step 1: Write ChassisStatusPoller**

```python
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
                    await self._merge_and_push(result["data"])
            except Exception:
                logger.exception("ChassisStatusPoller poll error")
            await asyncio.sleep(POLL_INTERVAL)

    async def _merge_and_push(self, chassis_data: dict):
        existing = self._status_service.get_latest(DEFAULT_ROBOT_ID) or {}

        position = {
            "x": float(chassis_data.get("world_x", 0.0)),
            "y": float(chassis_data.get("world_y", 0.0)),
            "theta": float(chassis_data.get("theta", 0.0)),
        }

        merged = {
            "position": position,
            "current_map": chassis_data.get("map_name", existing.get("current_map", "")),
            "battery": int(chassis_data.get("battery_percentage", existing.get("battery", 0))),
            "charging": bool(chassis_data.get("charge", 0)),
            "lift_height": existing.get("lift_height", 0.0),
            "gripper": existing.get("gripper", {
                "left": {"state": "open", "force": 0.0},
                "right": {"state": "open", "force": 0.0},
            }),
            "enabled": existing.get("enabled", False),
            "error_code": existing.get("error_code", 0),
            "task_status": existing.get("task_status", "idle"),
            "arm": existing.get("arm", {}),
        }

        await self._status_service.push_status(DEFAULT_ROBOT_ID, merged)
```

- [ ] **Step 2: Commit**

```bash
git add robot_control/backend/app/services/chassis_poller.py
git commit -m "feat: add ChassisStatusPoller for chassis hardware status polling"
```

---

## Task 3: Integrate ChassisStatusPoller into lifespan

**Files:**
- Modify: `robot_control/backend/app/main.py`

- [ ] **Step 1: Import and wire up**

At line 23, add import:

```python
from app.services.chassis_poller import ChassisStatusPoller
```

After line 59 (`app.state.chassis_client = chassis_client`), add:

```python
    # Chassis status poller (poll hardware status every 1s)
    chassis_poller = ChassisStatusPoller(chassis_client, status_service)
    await chassis_poller.start()
    app.state.chassis_poller = chassis_poller
```

In the shutdown block (after `await chassis_client.close()`), add:

```python
    await chassis_poller.stop()
```

The relevant section becomes:

```python
    # Chassis client (HTTP direct, no ROS2)
    settings = get_settings()
    try:
        chassis_client = ChassisClient(
            base_url=settings.chassis_base_url,
            user_code=settings.chassis_user_code,
            password=settings.chassis_password,
            timeout=settings.chassis_timeout,
        )
    except Exception:
        logger.warning("Failed to create ChassisClient, using mock")
        chassis_client = MockChassisClient()
    app.state.chassis_client = chassis_client

    # Chassis status poller (poll hardware status every 1s)
    chassis_poller = ChassisStatusPoller(chassis_client, status_service)
    await chassis_poller.start()
    app.state.chassis_poller = chassis_poller

    logger.info(...)
    yield

    # Shutdown
    await chassis_poller.stop()
    await chassis_client.close()
    ...
```

- [ ] **Step 2: Verify the file**

```bash
python -c "import ast; ast.parse(open('robot_control/backend/app/main.py').read()); print('Syntax OK')"
```

- [ ] **Step 3: Commit**

```bash
git add robot_control/backend/app/main.py
git commit -m "feat: integrate ChassisStatusPoller into application lifespan"
```

---

## Task 4: Fix dispatch config default port

**Files:**
- Modify: `dispatch/backend/app/core/config.py`

- [ ] **Step 1: Change port 9001 → 8000**

In the `Settings` class (lines 25-32), change:

```python
    robots: list[RobotConfig] = [
        RobotConfig(
            id="robot_001",
            name="1号机器人",
            control_url="http://127.0.0.1:8000",
            ws_url="ws://127.0.0.1:8000/ws/v1/status",
        )
    ]
```

- [ ] **Step 2: Update DB for existing installations**

```bash
sqlite3 dispatch/backend/data/dispatch.db "UPDATE robots SET control_url='http://127.0.0.1:8000', ws_url='ws://127.0.0.1:8000/ws/v1/status' WHERE id='robot_001';"
sqlite3 dispatch/backend/data/dispatch.db "SELECT id, control_url, ws_url FROM robots;"
```

Expected: `robot_001|http://127.0.0.1:8000|ws://127.0.0.1:8000/ws/v1/status`

- [ ] **Step 3: Commit**

```bash
git add dispatch/backend/app/core/config.py
git commit -m "fix: change default robot port 9001→8000 to match control system"
```

---

## Task 5: Fix RobotProxyService lazy client creation

**Files:**
- Modify: `dispatch/backend/app/services/robot_proxy.py`

- [ ] **Step 1: Remove pre-population from __init__**

Replace `__init__` (lines 12-16):

```python
    def __init__(self):
        self._clients: dict[str, RobotHttpClient] = {}
```

Remove the `settings = get_settings()` + loop block. The import of `get_settings` can also be removed from line 6.

- [ ] **Step 2: Verify _get_or_create_client handles everything**

The existing `_get_or_create_client` (lines 21-30) already does:
1. Check `self._clients` cache
2. If not found, query DB
3. If DB has robot, create client and cache it
4. Return None if not found

This is correct — no further changes needed. The `set_db()` call in `main.py:42` happens before any API request, so DB will be available.

- [ ] **Step 3: Verify syntax**

```bash
python -c "import ast; ast.parse(open('dispatch/backend/app/services/robot_proxy.py').read()); print('Syntax OK')"
```

- [ ] **Step 4: Commit**

```bash
git add dispatch/backend/app/services/robot_proxy.py
git commit -m "fix: use lazy DB-based client creation in RobotProxyService"
```

---

## Task 6: Run tests

- [ ] **Step 1: Run control system tests**

```bash
cd /home/kty/Desktop/furance_robot && python -m pytest robot_control/backend/tests/ -v --ignore=robot_control/backend/tests/test_moveit_client.py --ignore=robot_control/backend/tests/test_ros2_factory.py --ignore=robot_control/backend/tests/test_ros2_nodes_api.py
```

Expected: All tests PASS

- [ ] **Step 2: Run shared package tests**

```bash
cd /home/kty/Desktop/furance_robot && python -m pytest shared/tests/ -v
```

Expected: All tests PASS

# Control System — Chassis Status Polling & Dispatch Sync

## 1. Control System: Chassis Hardware Status Polling

### 1.1 New: `ChassisStatusPoller` (`robot_control/backend/app/services/chassis_poller.py`)

Background task that polls `GET /real_time_data/robot_hardware_status` every 1 second from the chassis HTTP API.

**Mapping chassis → status payload:**

| Chassis field | Status field | Notes |
|---|---|---|
| `world_x`, `world_y`, `theta` | `position.x`, `position.y`, `position.theta` | Direct mapping |
| `battery_percentage` | `battery` | int |
| `charge` (0/1) | `charging` (bool) | `charge == 1` → true |
| `map_name` | `current_map` | String |

### 1.2 Merge strategy with ROS2 topic data

The existing `RealRos2TopicListener` pushes `enabled`, `error_code`, `arm`, `gripper` from the `/robot_status` ROS2 topic. The poller and topic listener **both push full status snapshots**, but the poller reads the latest ROS2 data from `StatusService.get_latest()` before merging:

```
polled_chassis_data + existing_ros2_arm_data + existing_ros2_gripper_data → push_status
```

This avoids race conditions: each poll cycle constructs a complete status dict from both sources.

### 1.3 Lifecycle integration

In `main.py` lifespan:
- Startup: `chassis_poller = ChassisStatusPoller(chassis_client, status_service); await chassis_poller.start()`
- Shutdown: `await chassis_poller.stop()`

No change to the existing `topic_listener` or `joint_state_listener`.

---

## 2. Dispatch System: Port Fix

### 2.1 Config default (`dispatch/backend/app/core/config.py`)

Change `control_url` and `ws_url` defaults from port `9001` → `8000`:

```python
control_url="http://127.0.0.1:8000",
ws_url="ws://127.0.0.1:8000/ws/v1/status",
```

### 2.2 DB update

Run one-time: `UPDATE robots SET control_url='http://127.0.0.1:8000', ws_url='ws://127.0.0.1:8000/ws/v1/status' WHERE id='robot_001';`

---

## 3. Dispatch System: Workflow Proxy Fix

### 3.1 Problem

`RobotProxyService.__init__` creates `RobotHttpClient` instances from `settings.robots` (hardcoded defaults). Even after the DB update, the proxy uses the old port. `_get_or_create_client` does try DB lookup — but only for robots NOT in `self._clients`, and `robot_001` IS already in `self._clients` from `__init__`.

### 3.2 Fix: Lazy client creation

`RobotProxyService.__init__` is called before `set_db()` in `main.py`, so we can't query DB in `__init__`. Solution:

1. Make `__init__` stop pre-populating from `settings.robots` (remove the loop)
2. `_get_or_create_client` already does DB-first lookup, then fallback to settings. This becomes the sole client creation path.

No `set_db` call order change needed — it's already called right after `__init__` in `main.py:42`.

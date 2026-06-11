# 相机系统重构 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将相机系统从 ROS2 topic 订阅模式重构为 pyorbbecsdk 直连模式，支持多相机管理、WebSocket 视频推流、配置化相机位置绑定。

**Architecture:** camera_manager (pyorbbecsdk 直连 + 帧缓存) 和 camera_ws_handler (FastAPI WebSocket) 运行在 robot_control 进程内。camera_client 直接调用 camera_manager 方法获取相机列表和控制流，camera_ws_handler 直接调用同步 getter 获取帧数据推送前端。前端通过同一端口的 WebSocket 接收视频流，无跨域问题。

**Tech Stack:** Python 3.10, pyorbbecsdk, rclpy, FastAPI WebSocket, Vue 3, OpenCV, numpy

---

## 文件清单

| 文件 | 操作 | 职责 |
|------|------|------|
| `ros2_ws/.../vision/camera_config.yaml` | 创建 | 相机→位置绑定配置 |
| `ros2_ws/.../vision/camera_manager.py` | 创建 | 多相机生命周期管理 + 同步帧 API |
| `ros2_ws/.../vision/camera_ws_handler.py` | 创建 | WebSocket 推流处理器 |
| `robot_control/backend/app/ros2/camera_client.py` | 修改 | 改为调用 camera_manager 直连 |
| `robot_control/backend/app/api/camera.py` | 修改 | 新增 list，删除 publish/frame，改造 stream |
| `robot_control/backend/app/main.py` | 修改 | 初始化 camera_manager + mount WS router |
| `robot_control/frontend/src/api/camera.js` | 修改 | 新增 list，移除 getFrame |
| `robot_control/frontend/src/views/CameraView.vue` | 修改 | WS 推流 + 动态相机列表 |
| `robot_control/frontend/src/views/WorkflowEditor.vue` | 修改 | 视觉步骤相机选择动态获取 |

---

### Task 1: camera_config.yaml — 相机绑定配置

**Files:**
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_config.yaml`

- [ ] **Step 1: 创建配置文件**

```yaml
# 奥比中光相机 — 位置绑定配置
# 通过 serial 或 usb_port 匹配物理相机到逻辑 ID
# 匹配优先级: serial > usb_port

cameras:
  - id: "head"
    name: "头部相机"
    serial: "CP0E163000FP"
    usb_port: "2-1"
    position: "head"
    color_stream:
      width: 1280
      height: 720
      fps: 30
    depth_stream:
      width: 848
      height: 480
      fps: 30

  - id: "left_arm"
    name: "左臂相机"
    usb_port: "2-2"
    position: "left_arm"

  - id: "right_arm"
    name: "右臂相机"
    usb_port: "2-3"
    position: "right_arm"
```

- [ ] **Step 2: 验证 YAML 语法**

```bash
python3 -c "import yaml; yaml.safe_load(open('ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_config.yaml')); print('OK')"
```

- [ ] **Step 3: 提交**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_config.yaml
git commit -m "feat: add camera_config.yaml for position binding"
```

---

### Task 2: camera_manager.py — 核心相机管理器

**Files:**
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_manager.py`

- [ ] **Step 1: 创建 camera_manager.py 骨架和 LD_LIBRARY_PATH 处理**

```python
#!/usr/bin/env python3
"""
相机管理器 — 基于 pyorbbecsdk 直连奥比中光相机。

功能:
  - 读取 camera_config.yaml，按 serial/usb_port 匹配物理相机
  - 为每个相机管理 pyorbbecsdk.Pipeline 实例
  - 后台线程持续采集帧，缓存最新一帧
  - 提供同步 getter 方法供视觉算法和 WebSocket 推流使用
  - 作为 ROS2 Node 运行，暴露 Service 供 robot_control 调用

用法:
  from python_pkgs.vision.camera_manager import init_camera_manager, get_camera_manager

  # 在 robot_control 启动时初始化
  init_camera_manager(node, config_path)

  # 获取全局单例
  mgr = get_camera_manager()

  # 同步帧获取 (供算法开发)
  rgb = mgr.get_latest_color("head")       # np.ndarray (H, W, 3) BGR
  depth = mgr.get_latest_depth("head")     # np.ndarray (H, W) float32 mm
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LD_LIBRARY_PATH 修正: pyorbbecsdk pip 包自带的 libOrbbecSDK (v2.8.6)
# 必须优先于 ROS2 自带的旧版 (v2.7.6)
# ---------------------------------------------------------------------------
_SDK_LIB_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "lib", "python3.10",
    "site-packages", "pyorbbecsdk",
)
if os.path.isdir(_SDK_LIB_DIR):
    _current_ld = os.environ.get("LD_LIBRARY_PATH", "")
    _paths = _current_ld.split(":") if _current_ld else []
    if _SDK_LIB_DIR not in _paths:
        # 在服务器进程中不使用 os.execve（会重启整个服务），
        # 而是要求在启动脚本中预先设置 LD_LIBRARY_PATH
        logger.warning(
            "pyorbbecsdk lib dir not in LD_LIBRARY_PATH. "
            "Set before starting server: "
            "export LD_LIBRARY_PATH=%s:$LD_LIBRARY_PATH",
            _SDK_LIB_DIR,
        )

import cv2

# 全局单例
_camera_manager: Optional["CameraManager"] = None
```

- [ ] **Step 2: 添加 CameraInfo 数据类和配置加载**

```python
from dataclasses import dataclass, field


@dataclass
class CameraInfo:
    """单个相机的配置和状态信息。"""
    id: str
    name: str
    serial: str = ""
    usb_port: str = ""
    position: str = ""
    connected: bool = False
    color_width: int = 0
    color_height: int = 0
    color_fps: int = 0
    depth_width: int = 0
    depth_height: int = 0
    depth_fps: int = 0
    firmware_version: str = ""
    hardware_version: str = ""
    pid: int = 0
    vid: int = 0
    connection_type: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "serial": self.serial,
            "usb_port": self.usb_port,
            "position": self.position,
            "connected": self.connected,
            "color_width": self.color_width,
            "color_height": self.color_height,
            "color_fps": self.color_fps,
            "depth_width": self.depth_width,
            "depth_height": self.depth_height,
            "depth_fps": self.depth_fps,
            "firmware_version": self.firmware_version,
            "hardware_version": self.hardware_version,
            "pid": self.pid,
            "vid": self.vid,
            "connection_type": self.connection_type,
        }


def _load_config(config_path: str) -> list[dict]:
    """加载 YAML 配置文件，返回 cameras 列表。"""
    import yaml

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Camera config not found: {config_path}")
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("cameras", [])
```

- [ ] **Step 3: 添加 CameraManager 类 — 初始化和设备匹配**

```python
class CameraManager:
    """管理多个奥比中光相机，提供帧缓存和同步获取接口。"""

    def __init__(self, config_path: str):
        self._config_path = config_path
        self._cameras: dict[str, CameraInfo] = {}
        self._pipelines: dict[str, Any] = {}  # camera_id -> pyorbbecsdk.Pipeline
        self._streaming: dict[str, bool] = {}  # camera_id -> is_streaming

        # 帧缓存 (线程安全)
        self._lock = threading.Lock()
        self._color_frames: dict[str, Optional[np.ndarray]] = {}
        self._depth_frames: dict[str, Optional[np.ndarray]] = {}
        self._frame_timestamps: dict[str, float] = {}

        # 采集线程
        self._threads: dict[str, threading.Thread] = {}
        self._running = True

        self._init_cameras()

    def _init_cameras(self):
        """读取配置，发现并匹配物理相机。"""
        from pyorbbecsdk import Context, OBLogLevel

        configs = _load_config(self._config_path)

        ctx = Context()
        ctx.set_logger_level(OBLogLevel.WARNING)
        device_list = ctx.query_devices()

        # 构建设备查找表: serial -> device, usb_port -> device
        devices_by_serial: dict[str, Any] = {}
        devices_by_usb: dict[str, Any] = {}
        for i in range(device_list.get_count()):
            device = device_list.get_device_by_index(i)
            info = device.get_device_info()
            serial = info.get_serial_number()
            # usb_port 需要通过设备属性获取，这里先只用 serial 匹配
            if serial:
                devices_by_serial[serial] = device

        for cfg in configs:
            cam_id = cfg["id"]
            info = CameraInfo(
                id=cam_id,
                name=cfg.get("name", cam_id),
                serial=cfg.get("serial", ""),
                usb_port=cfg.get("usb_port", ""),
                position=cfg.get("position", ""),
            )

            # 匹配物理设备: serial 优先
            device = None
            if info.serial and info.serial in devices_by_serial:
                device = devices_by_serial[info.serial]

            if device is not None:
                dev_info = device.get_device_info()
                info.connected = True
                info.serial = dev_info.get_serial_number()
                info.firmware_version = dev_info.get_firmware_version()
                info.hardware_version = dev_info.get_hardware_version()
                info.pid = dev_info.get_pid()
                info.vid = dev_info.get_vid()
                info.connection_type = dev_info.get_connection_type()

                # 枚举默认流配置
                from pyorbbecsdk import OBSensorType, Pipeline
                pipeline = Pipeline(device)
                self._pipelines[cam_id] = pipeline

                try:
                    color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
                    cp = color_profiles.get_default_video_stream_profile()
                    info.color_width = cp.get_width()
                    info.color_height = cp.get_height()
                    info.color_fps = cp.get_fps()
                except Exception:
                    pass

                try:
                    depth_profiles = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
                    dp = depth_profiles.get_default_video_stream_profile()
                    info.depth_width = dp.get_width()
                    info.depth_height = dp.get_height()
                    info.depth_fps = dp.get_fps()
                except Exception:
                    pass

                # 覆盖配置中指定的流参数
                color_cfg = cfg.get("color_stream", {})
                if color_cfg:
                    if "width" in color_cfg:
                        info.color_width = color_cfg["width"]
                    if "height" in color_cfg:
                        info.color_height = color_cfg["height"]
                    if "fps" in color_cfg:
                        info.color_fps = color_cfg["fps"]

                depth_cfg = cfg.get("depth_stream", {})
                if depth_cfg:
                    if "width" in depth_cfg:
                        info.depth_width = depth_cfg["width"]
                    if "height" in depth_cfg:
                        info.depth_height = depth_cfg["height"]
                    if "fps" in depth_cfg:
                        info.depth_fps = depth_cfg["fps"]

                logger.info(
                    "Camera '%s' matched: serial=%s, color=%dx%d@%d, depth=%dx%d@%d",
                    cam_id, info.serial,
                    info.color_width, info.color_height, info.color_fps,
                    info.depth_width, info.depth_height, info.depth_fps,
                )
            else:
                logger.warning("Camera '%s' not found (serial=%s, usb=%s)",
                               cam_id, info.serial, info.usb_port)

            self._cameras[cam_id] = info
            self._streaming[cam_id] = False
            self._color_frames[cam_id] = None
            self._depth_frames[cam_id] = None
            self._frame_timestamps[cam_id] = 0.0

    # ---- 公共 API ----
```

- [ ] **Step 4: 添加 get_camera_list 和流控制方法**

```python
    def get_camera_list(self) -> list[dict]:
        """返回所有已配置相机的信息列表。"""
        return [info.to_dict() for info in self._cameras.values()]

    def start_stream(self, camera_id: str) -> dict:
        """启动指定相机的帧采集线程。"""
        if camera_id not in self._cameras:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}
        if not self._cameras[camera_id].connected:
            return {"success": False, "message": f"Camera not connected: {camera_id}"}
        if self._streaming.get(camera_id):
            return {"success": True, "message": f"Already streaming: {camera_id}"}

        pipeline = self._pipelines.get(camera_id)
        if pipeline is None:
            return {"success": False, "message": f"No pipeline for: {camera_id}"}

        # 启动 Pipeline
        from pyorbbecsdk import Config, OBSensorType, OBError
        config = Config()
        try:
            color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
            config.enable_stream(color_profiles.get_default_video_stream_profile())
        except OBError:
            pass
        try:
            depth_profiles = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
            config.enable_stream(depth_profiles.get_default_video_stream_profile())
        except OBError:
            pass

        try:
            pipeline.start(config)
        except OBError as e:
            return {"success": False, "message": f"Pipeline start failed: {e}"}

        self._streaming[camera_id] = True

        # 启动采集线程
        thread = threading.Thread(
            target=self._capture_loop,
            args=(camera_id,),
            daemon=True,
            name=f"cam-{camera_id}",
        )
        self._threads[camera_id] = thread
        thread.start()

        logger.info("Camera stream started: %s", camera_id)
        return {"success": True, "message": f"Streaming {camera_id}"}

    def stop_stream(self, camera_id: str) -> dict:
        """停止指定相机的帧采集。"""
        if camera_id not in self._cameras:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}

        self._streaming[camera_id] = False

        thread = self._threads.pop(camera_id, None)
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

        pipeline = self._pipelines.get(camera_id)
        if pipeline:
            try:
                pipeline.stop()
            except Exception:
                pass

        with self._lock:
            self._color_frames[camera_id] = None
            self._depth_frames[camera_id] = None

        logger.info("Camera stream stopped: %s", camera_id)
        return {"success": True, "message": f"Stopped {camera_id}"}
```

- [ ] **Step 5: 添加帧采集线程和同步 getter**

```python
    def _capture_loop(self, camera_id: str):
        """后台线程: 持续从 Pipeline 拉取帧并缓存。"""
        pipeline = self._pipelines[camera_id]
        fps = max(self._cameras[camera_id].color_fps, 15)
        interval = 1.0 / fps

        while self._running and self._streaming.get(camera_id, False):
            try:
                frames = pipeline.wait_for_frames(100)
                if frames is None:
                    time.sleep(0.01)
                    continue

                color_frame = frames.get_color_frame()
                depth_frame = frames.get_depth_frame()

                with self._lock:
                    if color_frame is not None:
                        self._color_frames[camera_id] = self._frame_to_bgr(color_frame)
                    if depth_frame is not None:
                        self._depth_frames[camera_id] = self._frame_to_depth_mm(depth_frame)
                    self._frame_timestamps[camera_id] = time.time()

            except Exception:
                logger.exception("Capture error for %s", camera_id)

            time.sleep(interval)

    @staticmethod
    def _frame_to_bgr(frame) -> Optional[np.ndarray]:
        """将 SDK VideoFrame 转为 BGR numpy 数组。"""
        from pyorbbecsdk import OBFormat

        width = frame.get_width()
        height = frame.get_height()
        fmt = frame.get_format()
        data = np.asanyarray(frame.get_data())

        if fmt == OBFormat.RGB:
            img = data.reshape((height, width, 3))
            return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        elif fmt == OBFormat.BGR:
            return data.reshape((height, width, 3))
        elif fmt == OBFormat.YUYV:
            img = data.reshape((height, width, 2))
            return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_YUYV)
        elif fmt == OBFormat.MJPG:
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
        elif fmt == OBFormat.I420:
            y = data[:height, :]
            u = data[height:height + height // 4].reshape(height // 2, width // 2)
            v = data[height + height // 4:].reshape(height // 2, width // 2)
            yuv = cv2.merge([y, u, v])
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
        elif fmt == OBFormat.NV12:
            y = data[:height, :]
            uv = data[height:height + height // 2].reshape(height // 2, width)
            yuv = cv2.merge([y, uv])
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV12)
        elif fmt == OBFormat.NV21:
            y = data[:height, :]
            uv = data[height:height + height // 2].reshape(height // 2, width)
            yuv = cv2.merge([y, uv])
            return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_NV21)
        elif fmt == OBFormat.UYVY:
            img = data.reshape((height, width, 2))
            return cv2.cvtColor(img, cv2.COLOR_YUV2BGR_UYVY)
        else:
            logger.warning("Unsupported color format: %s", fmt)
            return None

    @staticmethod
    def _frame_to_depth_mm(frame) -> np.ndarray:
        """将 SDK DepthFrame 转为 float32 mm 数组。"""
        width = frame.get_width()
        height = frame.get_height()
        scale = frame.get_depth_scale()
        raw = np.frombuffer(frame.get_data(), dtype=np.uint16)
        return raw.reshape((height, width)).astype(np.float32) * scale

    # ---- 同步帧获取 (供视觉算法和 WebSocket 推流) ----

    def get_latest_color(self, camera_id: str) -> Optional[np.ndarray]:
        """返回最新彩色帧的拷贝 (BGR, HxWx3)。可能为 None。"""
        with self._lock:
            frame = self._color_frames.get(camera_id)
            return frame.copy() if frame is not None else None

    def get_latest_depth(self, camera_id: str) -> Optional[np.ndarray]:
        """返回最新深度帧的拷贝 (float32 mm, HxW)。可能为 None。"""
        with self._lock:
            frame = self._depth_frames.get(camera_id)
            return frame.copy() if frame is not None else None

    def get_frame_timestamp(self, camera_id: str) -> float:
        """返回最新帧的时间戳 (time.time())。"""
        with self._lock:
            return self._frame_timestamps.get(camera_id, 0.0)

    def is_streaming(self, camera_id: str) -> bool:
        return self._streaming.get(camera_id, False)

    # ---- 生命周期 ----

    def shutdown(self):
        """停止所有相机流并释放资源。"""
        self._running = False
        for cam_id in list(self._streaming.keys()):
            if self._streaming[cam_id]:
                self.stop_stream(cam_id)
        logger.info("CameraManager shutdown complete")
```

- [ ] **Step 6: 添加模块级初始化和单例访问函数**

```python
def init_camera_manager(config_path: str) -> CameraManager:
    """初始化全局相机管理器单例。在 robot_control 启动时调用一次。"""
    global _camera_manager
    if _camera_manager is not None:
        logger.warning("CameraManager already initialized, shutting down old instance")
        _camera_manager.shutdown()
    _camera_manager = CameraManager(config_path)
    logger.info("CameraManager initialized with config: %s", config_path)
    return _camera_manager


def get_camera_manager() -> Optional[CameraManager]:
    """获取全局相机管理器单例。未初始化时返回 None。"""
    return _camera_manager


def shutdown_camera_manager():
    """关闭全局相机管理器。"""
    global _camera_manager
    if _camera_manager is not None:
        _camera_manager.shutdown()
        _camera_manager = None
```

- [ ] **Step 7: 验证语法**

```bash
python3 -c "import ast; ast.parse(open('ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_manager.py').read()); print('Syntax OK')"
```

- [ ] **Step 8: 提交**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_manager.py
git commit -m "feat: add camera_manager with pyorbbecsdk direct control"
```

---

### Task 3: camera_ws_handler.py — WebSocket 推流处理器

**Files:**
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_ws_handler.py`

- [ ] **Step 1: 创建 camera_ws_handler.py**

```python
"""
WebSocket 相机推流处理器。

挂载到 robot_control FastAPI 的 /ws/v1/camera 端点。
从 camera_manager 获取最新帧，编码为 JPEG base64 推送给前端。

协议:
  前端 → 服务端: {"action": "subscribe", "camera_id": "head", "stream_type": "raw"}
  服务端 → 前端: {"type": "frame", "camera_id": "head", "stream_type": "raw", "data": "<base64>"}
  服务端 → 前端: {"type": "error", "message": "..."}
  前端 → 服务端: {"action": "unsubscribe"}
"""

import asyncio
import base64
import json
import logging
import time

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# stream_type -> 渲染函数
# 后续可扩展 annotated 类型

MIN_DEPTH_MM = 100
MAX_DEPTH_MM = 5000


def _render_depth_3d(depth_mm: np.ndarray) -> np.ndarray:
    """将 float32 深度图渲染为 3D 浮雕 BGR 图像。"""
    depth_clipped = np.clip(depth_mm, MIN_DEPTH_MM, MAX_DEPTH_MM)
    depth_norm = (depth_clipped - MIN_DEPTH_MM) / (MAX_DEPTH_MM - MIN_DEPTH_MM + 1e-6)
    depth_gamma = np.power(depth_norm, 0.8)
    depth_8bit = (depth_gamma * 255).astype(np.uint8)

    grad_x = cv2.Scharr(depth_8bit, cv2.CV_32F, 1, 0)
    grad_y = cv2.Scharr(depth_8bit, cv2.CV_32F, 0, 1)
    mag = cv2.magnitude(grad_x, grad_y) + 1.0

    lighting = -0.707 * (grad_x + grad_y) / mag
    lighting = lighting * 0.15 + 0.85
    np.clip(lighting, 0.7, 1.0, out=lighting)

    depth_colored = cv2.applyColorMap(depth_8bit, cv2.COLORMAP_JET)
    depth_colored = (depth_colored * lighting[..., np.newaxis]).astype(np.uint8)
    return depth_colored


def _frame_to_jpeg_base64(frame: np.ndarray) -> str:
    """将 numpy 图像编码为 JPEG base64 字符串。"""
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(jpeg.tobytes()).decode("ascii")


@router.websocket("/ws/v1/camera")
async def camera_websocket(websocket: WebSocket):
    """相机视频推流 WebSocket 端点。"""
    from python_pkgs.vision.camera_manager import get_camera_manager

    await websocket.accept()

    camera_id: str | None = None
    stream_type: str = "raw"
    push_task: asyncio.Task | None = None

    async def push_frames():
        """后台协程: 从 camera_manager 获取帧并推送。"""
        manager = get_camera_manager()
        if manager is None:
            await websocket.send_json({"type": "error", "message": "CameraManager not initialized"})
            return

        last_ts = 0.0
        # 根据相机帧率计算推送间隔
        fps = 15  # 默认 15fps
        if camera_id:
            for cam in manager.get_camera_list():
                if cam["id"] == camera_id:
                    fps = max(cam.get("color_fps", 15), 15)
                    break
        interval = 1.0 / fps

        while True:
            try:
                if camera_id is None:
                    await asyncio.sleep(0.1)
                    continue

                ts = manager.get_frame_timestamp(camera_id)
                if ts == last_ts:
                    # 帧未更新，跳过
                    await asyncio.sleep(0.01)
                    continue
                last_ts = ts

                if stream_type == "depth":
                    frame = manager.get_latest_depth(camera_id)
                    if frame is not None:
                        frame = _render_depth_3d(frame)
                else:
                    frame = manager.get_latest_color(camera_id)

                if frame is None:
                    await asyncio.sleep(0.01)
                    continue

                jpeg_b64 = _frame_to_jpeg_base64(frame)
                await websocket.send_json({
                    "type": "frame",
                    "camera_id": camera_id,
                    "stream_type": stream_type,
                    "data": jpeg_b64,
                })

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Push error for %s", camera_id)
                await asyncio.sleep(0.1)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action", "")

            if action == "subscribe":
                camera_id = msg.get("camera_id", "")
                stream_type = msg.get("stream_type", "raw")

                manager = get_camera_manager()
                if manager is None:
                    await websocket.send_json({"type": "error", "message": "CameraManager not initialized"})
                    continue

                # 检查相机是否存在
                cam_list = [c["id"] for c in manager.get_camera_list()]
                if camera_id not in cam_list:
                    await websocket.send_json({"type": "error", "message": f"Camera not found: {camera_id}"})
                    continue

                # 确保相机流已启动
                if not manager.is_streaming(camera_id):
                    result = manager.start_stream(camera_id)
                    if not result["success"]:
                        await websocket.send_json({"type": "error", "message": result["message"]})
                        continue

                # 启动推送协程
                if push_task:
                    push_task.cancel()
                push_task = asyncio.create_task(push_frames())
                logger.info("WS subscribe: camera=%s, stream_type=%s", camera_id, stream_type)

            elif action == "unsubscribe":
                if push_task:
                    push_task.cancel()
                    push_task = None
                camera_id = None
                logger.info("WS unsubscribe")

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        logger.info("WS disconnected: camera=%s", camera_id)
    finally:
        if push_task:
            push_task.cancel()
```

- [ ] **Step 2: 验证语法**

```bash
python3 -c "import ast; ast.parse(open('ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_ws_handler.py').read()); print('Syntax OK')"
```

- [ ] **Step 3: 提交**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_ws_handler.py
git commit -m "feat: add camera_ws_handler for WebSocket video streaming"
```

---

### Task 4: camera_client.py — 改造为调用 camera_manager

**Files:**
- Modify: `robot_control/backend/app/ros2/camera_client.py`

- [ ] **Step 1: 读取当前文件确认内容**

```bash
wc -l robot_control/backend/app/ros2/camera_client.py
```

- [ ] **Step 2: 重写 camera_client.py**

用以下完整内容替换整个文件：

```python
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

try:
    from rclpy.node import Node
    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class CameraClientBase(ABC):
    @abstractmethod
    async def get_camera_list(self) -> dict[str, Any]:
        """返回所有已配置相机的信息列表。"""
        ...

    @abstractmethod
    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        """执行视觉检测，返回抓取位姿。"""
        ...

    @abstractmethod
    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        """启动指定相机的帧采集。"""
        ...

    @abstractmethod
    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        """停止指定相机的帧采集。"""
        ...


class MockCameraClient(CameraClientBase):
    def __init__(self):
        self._mock_cameras = [
            {
                "id": "head", "name": "头部相机 (Mock)", "position": "head",
                "connected": True, "serial": "MOCK001",
                "color_width": 1280, "color_height": 720, "color_fps": 30,
                "depth_width": 848, "depth_height": 480, "depth_fps": 30,
            },
            {
                "id": "left_arm", "name": "左臂相机 (Mock)", "position": "left_arm",
                "connected": True, "serial": "MOCK002",
                "color_width": 640, "color_height": 480, "color_fps": 30,
                "depth_width": 640, "depth_height": 400, "depth_fps": 30,
            },
            {
                "id": "right_arm", "name": "右臂相机 (Mock)", "position": "right_arm",
                "connected": False, "serial": "",
                "color_width": 0, "color_height": 0, "color_fps": 0,
                "depth_width": 0, "depth_height": 0, "depth_fps": 0,
            },
        ]

    async def get_camera_list(self) -> dict[str, Any]:
        return {"success": True, "cameras": self._mock_cameras}

    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        return {
            "success": True,
            "message": f"mock: detection on {camera_id} scene={scene}",
            "data": {
                "grasp_pose": {
                    "x": 350.0, "y": -120.0, "z": 200.0,
                    "roll": 180.0, "pitch": 0.0, "yaw": 90.0,
                },
                "confidence": 0.95,
            },
        }

    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        return {"success": True, "message": f"mock: streaming {camera_id} {stream_type}"}

    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        return {"success": True, "message": f"mock: stopped {camera_id}"}


class RealCameraClient(CameraClientBase):
    """通过 camera_manager 管理相机 (pyorbbecsdk 直连)。

    不再直接订阅 ROS2 topic。帧获取由 camera_ws_handler 通过
    camera_manager 的同步 getter 完成。
    detect_grasp_pose 仍需要 ROS2 runtime 来调用 VisionDetect service。
    """

    def __init__(self, runtime=None, timeout: float = 10.0):
        self._runtime = runtime  # 仅用于 detect_grasp_pose
        self._timeout = timeout

    async def get_camera_list(self) -> dict[str, Any]:
        from python_pkgs.vision.camera_manager import get_camera_manager

        mgr = get_camera_manager()
        if mgr is None:
            return {"success": False, "message": "CameraManager not initialized"}
        return {"success": True, "cameras": mgr.get_camera_list()}

    async def detect_grasp_pose(self, camera_id: str, scene: str) -> dict[str, Any]:
        """调用 ROS2 VisionDetect service (保留原有逻辑)。"""
        if self._runtime is None:
            return {"success": False, "message": "ROS2 runtime not available for VisionDetect"}

        from control_interfaces.srv import VisionDetect
        from rclpy.node import Node

        node: Node = self._runtime.node
        client = node.create_client(VisionDetect, "/vision_detect")
        if not client.wait_for_service(timeout_sec=5.0):
            return {"success": False, "message": "VisionDetect service not available"}

        req = VisionDetect.Request()
        req.camera_id = camera_id
        req.scene = scene
        result = await self._bridge_future(client.call_async(req))
        if result.get("success"):
            return {
                "success": True,
                "message": "Detection completed",
                "data": {
                    "grasp_pose": {
                        "x": result.get("x", 0.0),
                        "y": result.get("y", 0.0),
                        "z": result.get("z", 0.0),
                        "roll": result.get("roll", 0.0),
                        "pitch": result.get("pitch", 0.0),
                        "yaw": result.get("yaw", 0.0),
                    },
                },
            }
        return result

    async def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict[str, Any]:
        from python_pkgs.vision.camera_manager import get_camera_manager

        mgr = get_camera_manager()
        if mgr is None:
            return {"success": False, "message": "CameraManager not initialized"}
        return mgr.start_stream(camera_id)

    async def stop_stream(self, camera_id: str) -> dict[str, Any]:
        from python_pkgs.vision.camera_manager import get_camera_manager

        mgr = get_camera_manager()
        if mgr is None:
            return {"success": False, "message": "CameraManager not initialized"}
        return mgr.stop_stream(camera_id)

    async def _bridge_future(self, ros_future) -> dict[str, Any]:
        import asyncio

        loop = asyncio.get_event_loop()
        aio_future = loop.create_future()

        def _done_callback(fut):
            if aio_future.done():
                return
            try:
                response = fut.result()
                result = {
                    "success": bool(response.success),
                    "message": getattr(response, "message", ""),
                    "x": getattr(response, "x", 0.0),
                    "y": getattr(response, "y", 0.0),
                    "z": getattr(response, "z", 0.0),
                    "roll": getattr(response, "roll", 0.0),
                    "pitch": getattr(response, "pitch", 0.0),
                    "yaw": getattr(response, "yaw", 0.0),
                }
                loop.call_soon_threadsafe(aio_future.set_result, result)
            except Exception as exc:
                loop.call_soon_threadsafe(aio_future.set_exception, exc)

        ros_future.add_done_callback(_done_callback)

        try:
            return await asyncio.wait_for(aio_future, timeout=self._timeout)
        except asyncio.TimeoutError:
            return {"success": False, "message": f"Service timed out after {self._timeout}s"}
```

> **注意**: `RealCameraClient.__init__` 接收 `runtime` 仅用于 `detect_grasp_pose()`。其他方法通过 `camera_manager` 直连，不需要 ROS2。

- [ ] **Step 3: 验证语法**

```bash
python3 -c "import ast; ast.parse(open('robot_control/backend/app/ros2/camera_client.py').read()); print('Syntax OK')"
```

- [ ] **Step 4: 提交**

```bash
git add robot_control/backend/app/ros2/camera_client.py
git commit -m "refactor: camera_client uses camera_manager instead of ROS2 topics"
```

---

### Task 5: camera.py API — 改造路由

**Files:**
- Modify: `robot_control/backend/app/api/camera.py`

- [ ] **Step 1: 重写 camera.py**

用以下内容替换整个文件：

```python
from fastapi import APIRouter, Request
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/robot/{robot_id}/camera", tags=["camera"])


def _get_client(request: Request):
    return request.app.state.ros2.camera_client


@router.get("/list", response_model=ApiResponse)
async def list_cameras(robot_id: str, request: Request):
    """获取所有已配置相机的列表和信息。"""
    result = await _get_client(request).get_camera_list()
    if not result.get("success"):
        return ApiResponse(code=3001, message=result.get("message", "Failed to get camera list"))
    return ApiResponse(data=result.get("cameras", []))


@router.post("/stream/start", response_model=ApiResponse)
async def start_stream(robot_id: str, req: dict, request: Request):
    """启动相机帧采集: {"camera_id": "head", "stream_type": "raw"}"""
    camera_id = req.get("camera_id", "head")
    stream_type = req.get("stream_type", "raw")
    result = await _get_client(request).start_stream(camera_id, stream_type)
    return ApiResponse(data=result)


@router.post("/stream/stop", response_model=ApiResponse)
async def stop_stream(robot_id: str, req: dict, request: Request):
    """停止相机帧采集: {"camera_id": "head"}"""
    camera_id = req.get("camera_id", "head")
    result = await _get_client(request).stop_stream(camera_id)
    return ApiResponse(data=result)


@router.post("/detect", response_model=ApiResponse)
async def detect(robot_id: str, req: dict, request: Request):
    """执行视觉检测: {"camera_id": "head", "scene": "grasp_top"}"""
    camera_id = req.get("camera_id", "head")
    scene = req.get("scene", "")
    result = await _get_client(request).detect_grasp_pose(camera_id, scene)
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "Detection failed"))
    return ApiResponse(data=result.get("data", result))
```

- [ ] **Step 2: 验证语法**

```bash
python3 -c "import ast; ast.parse(open('robot_control/backend/app/api/camera.py').read()); print('Syntax OK')"
```

- [ ] **Step 3: 提交**

```bash
git add robot_control/backend/app/api/camera.py
git commit -m "refactor: camera API — add /list, remove publish/frame, simplify stream"
```

---

### Task 6: main.py — 初始化 camera_manager 并挂载 WS router

**Files:**
- Modify: `robot_control/backend/app/main.py`

- [ ] **Step 1: 在 lifespan startup 中添加 camera_manager 初始化**

在 `main.py` 的 `lifespan` 函数中，`app.state.ros2 = components` 之后，添加 camera_manager 初始化：

```python
    # Store on app.state for access from API endpoints and WS handlers
    app.state.ros2 = components

    # ---- 新增: 初始化相机管理器 ----
    from python_pkgs.vision.camera_manager import init_camera_manager
    config_path = os.environ.get(
        "CAMERA_CONFIG_PATH",
        str(Path(__file__).resolve().parent.parent.parent.parent.parent
            / "ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_config.yaml"),
    )
    try:
        init_camera_manager(config_path)
        logger.info("CameraManager initialized")
    except Exception:
        logger.exception("Failed to initialize CameraManager")
    # ---- 新增结束 ----
```

在 `lifespan` 的 shutdown 部分，添加 camera_manager 关闭：

```python
    # Shutdown
    # ---- 新增: 关闭相机管理器 ----
    from python_pkgs.vision.camera_manager import shutdown_camera_manager
    shutdown_camera_manager()
    # ---- 新增结束 ----
    await chassis_client.close()
```

- [ ] **Step 2: 挂载 camera_ws_handler 的 router**

在 `create_app` 函数中，添加 WS router：

```python
    app.include_router(camera_router)
    app.include_router(log_viewer_router)
    app.include_router(status_ws_router)
    app.include_router(logs_ws_router)

    # ---- 新增: 挂载相机 WebSocket 推流路由 ----
    from python_pkgs.vision.camera_ws_handler import router as camera_ws_router
    app.include_router(camera_ws_router)
    # ---- 新增结束 ----
```

- [ ] **Step 3: 修复 camera_ws_handler 中 router prefix 冲突**

`camera_ws_handler.py` 中的 WebSocket 路径是 `/ws/v1/camera`，而 `status_ws_router` 已经占用了 `/ws/v1/status`。两者不会冲突，但需要确认 `camera_ws_handler.py` 的 router 没有额外的 prefix。

确认 `camera_ws_handler.py` 中 `@router.websocket("/ws/v1/camera")` 路径是正确的，并且 router 没有 `prefix` 参数。

- [ ] **Step 4: 处理 factory.py 中 camera_client 构造**

修改 `robot_control/backend/app/ros2/factory.py`：

```python
# Real mode 下 camera_client 构造 (保持 runtime 引用，仅用于 detect_grasp_pose):
camera_client=RealCameraClient(runtime=runtime, timeout=settings.ros2_service_timeout),
```

Mock mode 不变（`MockCameraClient()` 无需 runtime）。

- [ ] **Step 5: 验证语法**

```bash
python3 -c "import ast; ast.parse(open('robot_control/backend/app/main.py').read()); print('Syntax OK')"
python3 -c "import ast; ast.parse(open('robot_control/backend/app/ros2/factory.py').read()); print('Syntax OK')"
```

- [ ] **Step 6: 提交**

```bash
git add robot_control/backend/app/main.py robot_control/backend/app/ros2/factory.py
git commit -m "feat: integrate camera_manager and camera_ws_handler into main"
```

---

### Task 7: camera.js — 前端 API 改造

**Files:**
- Modify: `robot_control/frontend/src/api/camera.js`

- [ ] **Step 1: 重写 camera.js**

```javascript
import api from '.'

const ROBOT_ID = 'robot_001'

export const cameraApi = {
  /** 获取相机列表 */
  list: () => api.get(`/robot/${ROBOT_ID}/camera/list`),

  /** 启动相机帧采集 */
  startStream: (cameraId, streamType = 'raw') =>
    api.post(`/robot/${ROBOT_ID}/camera/stream/start`, {
      camera_id: cameraId,
      stream_type: streamType,
    }),

  /** 停止相机帧采集 */
  stopStream: (cameraId) =>
    api.post(`/robot/${ROBOT_ID}/camera/stream/stop`, {
      camera_id: cameraId,
    }),

  /** 执行视觉检测 */
  detect: (cameraId, scene) =>
    api.post(`/robot/${ROBOT_ID}/camera/detect`, {
      camera_id: cameraId,
      scene,
    }),
}
```

- [ ] **Step 2: 提交**

```bash
git add robot_control/frontend/src/api/camera.js
git commit -m "refactor: camera.js — add list, remove getFrame and publish"
```

---

### Task 8: CameraView.vue — WebSocket 推流改造

**Files:**
- Modify: `robot_control/frontend/src/views/CameraView.vue`

- [ ] **Step 1: 重写 CameraView.vue 的 `<script setup>` 部分**

保持 template 和 style 不变（已有的 UI 布局合理），只替换 `<script setup>` 部分：

```javascript
<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { cameraApi } from '../api/camera'
import { ElMessage } from 'element-plus'
import { View, Aim, VideoCamera } from '@element-plus/icons-vue'

const poseFields = ['x', 'y', 'z', 'roll', 'pitch', 'yaw']

// ---- 相机列表 ----
const cameras = ref([])
const cameraId = ref('head')
const streamType = ref('raw')
const streaming = ref(false)
const connecting = ref(false)

// ---- 视觉检测 ----
const detectScene = ref('grasp_top')
const detecting = ref(false)
const detectResult = ref(null)

// ---- WebSocket ----
let ws = null
const frameData = ref('')

const streamTypeLabel = computed(() => {
  const labels = { raw: '原始画面', depth: '深度图', annotated: '带框标注' }
  return labels[streamType.value] || streamType.value
})

// 加载相机列表
async function loadCameras() {
  try {
    const res = await cameraApi.list()
    cameras.value = res.data || []
    if (cameras.value.length > 0 && !cameras.value.find(c => c.id === cameraId.value)) {
      cameraId.value = cameras.value[0].id
    }
  } catch (e) {
    ElMessage.error('获取相机列表失败')
    cameras.value = []
  }
}

onMounted(loadCameras)

onUnmounted(() => {
  disconnectStream()
})

watch(() => cameraId.value, () => {
  if (streaming.value) {
    disconnectStream()
    setTimeout(connectStream, 300)
  }
})

// ---- WebSocket 连接 ----

function getWsUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/v1/camera`
}

async function connectStream() {
  connecting.value = true
  try {
    // 先通过 HTTP 启动相机流采集
    await cameraApi.startStream(cameraId.value, streamType.value)

    // 建立 WebSocket 连接
    const url = getWsUrl()
    ws = new WebSocket(url)

    ws.onopen = () => {
      // 订阅指定相机和视频类型
      ws.send(JSON.stringify({
        action: 'subscribe',
        camera_id: cameraId.value,
        stream_type: streamType.value,
      }))
      streaming.value = true
      connecting.value = false
      ElMessage.success(`已连接 ${cameraId.value}`)
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'frame' && msg.data) {
          frameData.value = 'data:image/jpeg;base64,' + msg.data
        } else if (msg.type === 'error') {
          ElMessage.error(msg.message)
        }
      } catch (e) {
        // ignore parse errors
      }
    }

    ws.onerror = () => {
      ElMessage.error('WebSocket 连接错误')
      disconnectStream()
    }

    ws.onclose = () => {
      if (streaming.value) {
        streaming.value = false
        frameData.value = ''
      }
    }
  } catch (error) {
    ElMessage.error(error.message || '连接失败')
    connecting.value = false
  }
}

function disconnectStream() {
  if (ws) {
    try {
      ws.send(JSON.stringify({ action: 'unsubscribe' }))
    } catch (e) { /* ignore */ }
    ws.close()
    ws = null
  }
  streaming.value = false
  frameData.value = ''
  // 异步停止流采集
  cameraApi.stopStream(cameraId.value).catch(() => {})
}

// ---- 视觉检测 ----

async function runDetection() {
  detecting.value = true
  try {
    const res = await cameraApi.detect(cameraId.value, detectScene.value)
    const data = res.data?.data || res.data
    detectResult.value = data?.grasp_pose || data
    ElMessage.success('检测完成')
  } catch (error) {
    ElMessage.error(error.message || '检测失败')
  } finally {
    detecting.value = false
  }
}
</script>
```

- [ ] **Step 2: 更新 template 中相机选择下拉为动态选项**

将硬编码的相机选择：
```html
<el-select v-model="cameraId" style="width: 100%" @change="onCameraChange">
  <el-option label="相机 1" value="camera_1" />
  <el-option label="相机 2" value="camera_2" />
  <el-option label="相机 3" value="camera_3" />
</el-select>
```

替换为：
```html
<el-select v-model="cameraId" style="width: 100%" @change="onCameraChange">
  <el-option
    v-for="cam in cameras"
    :key="cam.id"
    :label="`${cam.name} (${cam.id})`"
    :value="cam.id"
    :disabled="!cam.connected"
  />
</el-select>
```

- [ ] **Step 3: 更新 template 中视频渲染**

将 `<img :src="frameSrc" ...>` 替换为：
```html
<img
  v-if="streaming && frameData"
  :src="frameData"
  class="video-frame"
  alt="Camera feed"
/>
```

- [ ] **Step 4: 更新视频类型下拉**

将 `grayscale` 选项改为 `annotated`：
```html
<el-select v-model="streamType" style="width: 100%" :disabled="streaming">
  <el-option label="原始画面" value="raw" />
  <el-option label="深度图" value="depth" />
  <el-option label="带框标注" value="annotated" :disabled="true" />
</el-select>
```

`annotated` 预留 disabled，后续视觉算法集成后启用。

- [ ] **Step 5: 移除 onFrameError 函数和 refreshTimer 相关代码**

删除 template 中 `@error="onFrameError"` 属性，删除 script 中 `onFrameError`、`startFrameRefresh`、`stopFrameRefresh`、`refreshTimer`、`publishing` 相关代码。

- [ ] **Step 6: 提交**

```bash
git add robot_control/frontend/src/views/CameraView.vue
git commit -m "refactor: CameraView uses WebSocket streaming with dynamic camera list"
```

---

### Task 9: WorkflowEditor.vue — 视觉步骤相机选择动态化

**Files:**
- Modify: `robot_control/frontend/src/views/WorkflowEditor.vue`

- [ ] **Step 1: 添加相机列表数据**

在 `<script setup>` 中添加：

```javascript
// 在 teachPresets 附近添加
const cameraList = ref([])

// 在 onMounted 中添加
async function loadCameraList() {
  try {
    const { cameraApi } = await import('../api/camera')
    const res = await cameraApi.list()
    cameraList.value = res.data || []
  } catch {
    cameraList.value = []
  }
}
```

在 `onMounted` 中调用 `loadCameraList()`。

- [ ] **Step 2: 更新视觉步骤中相机选择下拉**

将模板中 visual step 的相机选择（约第 314 行）：
```html
<el-select v-model="step.config.camera_id" size="small" style="width: 100%">
  <el-option label="相机 1" value="camera_1" />
  <el-option label="相机 2" value="camera_2" />
  <el-option label="相机 3" value="camera_3" />
</el-select>
```

替换为：
```html
<el-select v-model="step.config.camera_id" size="small" style="width: 100%">
  <el-option
    v-for="cam in cameraList"
    :key="cam.id"
    :label="`${cam.name} (${cam.id})`"
    :value="cam.id"
    :disabled="!cam.connected"
  />
</el-select>
```

- [ ] **Step 3: 更新 addStep 中 vision 默认值**

将 `vision: { camera_id: 'camera_1', scene: '' }` 改为使用 `cameraList` 中第一个可用相机：

```javascript
vision: { camera_id: cameraList.value.find(c => c.connected)?.id || 'head', scene: '' },
```

- [ ] **Step 4: 更新 selectWorkflow 中 vision 默认 camera_id**

将 `if (s.type === 'vision' && !s.config.camera_id) s.config.camera_id = 'camera_1'` 改为：

```javascript
if (s.type === 'vision' && !s.config.camera_id) {
  s.config.camera_id = cameraList.value.find(c => c.connected)?.id || 'head'
}
```

- [ ] **Step 5: 提交**

```bash
git add robot_control/frontend/src/views/WorkflowEditor.vue
git commit -m "refactor: WorkflowEditor camera selection dynamic from API"
```

---

## 验证检查

实现完成后，执行以下验证：

1. **后端启动验证** (mock 模式):
```bash
cd robot_control/backend
ROS2_MODE=mock python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 访问 http://localhost:8000/api/v1/robot/robot_001/camera/list
# 预期: 返回 Mock 相机列表
```

2. **后端启动验证** (real 模式, 需连接相机):
```bash
cd robot_control/backend
LD_LIBRARY_PATH=$HOME/.local/lib/python3.10/site-packages/pyorbbecsdk:$LD_LIBRARY_PATH \
ROS2_MODE=real python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 访问 /api/v1/robot/robot_001/camera/list
# 预期: 返回真实相机列表
```

3. **前端验证**:
```bash
cd robot_control/frontend
npm run dev
# 访问 http://localhost:3000/camera
# 预期: 相机列表动态加载，点击连接后显示视频流
```

4. **工作流编辑器验证**:
```bash
# 访问 http://localhost:3000/workflow
# 添加视觉步骤 → 相机下拉应显示动态列表
```

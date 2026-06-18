#!/usr/bin/env python3
"""
相机管理节点 — ROS2 Node，通过 pyorbbecsdk 直连奥比中光相机。

功能:
  - 读取 camera_config.yaml，按 serial 匹配物理相机
  - 管理多相机 Pipeline，后台线程采集帧
  - ROS2 Service: /camera/list, /camera/stream/start, /camera/stream/stop
  - WebSocket Server (localhost:8766): 视频帧推流

注册到 node_manager: NODE_REGISTRY['camera_manager']
"""

import asyncio
import base64
import json
import logging
import os
import sys
import threading

# ---- pyorbbecsdk 原生库路径修复 ----
# 必须在 import pyorbbecsdk 之前设置 LD_LIBRARY_PATH
_SDK_LIB_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "lib", "python3.10",
    "site-packages", "pyorbbecsdk",
)
if os.path.isdir(_SDK_LIB_DIR):
    _ld = os.environ.get("LD_LIBRARY_PATH", "")
    if _SDK_LIB_DIR not in _ld.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{_SDK_LIB_DIR}:{_ld}" if _ld else _SDK_LIB_DIR
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("orbbec_vision.camera_manager")

# ---------------------------------------------------------------------------
# LD_LIBRARY_PATH 修正
# ---------------------------------------------------------------------------
_SDK_LIB_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "lib", "python3.10",
    "site-packages", "pyorbbecsdk",
)
if os.path.isdir(_SDK_LIB_DIR):
    _current_ld = os.environ.get("LD_LIBRARY_PATH", "")
    if _SDK_LIB_DIR not in _current_ld.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{_SDK_LIB_DIR}:{_current_ld}" if _current_ld else _SDK_LIB_DIR
        os.execve(sys.executable, [sys.executable] + sys.argv, os.environ)

import cv2

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
WS_HOST = "127.0.0.1"
WS_PORT = 8766
MIN_DEPTH_MM = 100
MAX_DEPTH_MM = 5000

_DEFAULT_CONFIG = None  # resolved at runtime via ament_index


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class CameraInfo:
    id: str
    name: str = ""
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
    ir_width: int = 0
    ir_height: int = 0
    ir_fps: int = 0
    firmware_version: str = ""
    hardware_version: str = ""
    pid: int = 0
    vid: int = 0
    connection_type: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "serial": self.serial,
            "usb_port": self.usb_port, "position": self.position,
            "connected": self.connected,
            "color_width": self.color_width, "color_height": self.color_height,
            "color_fps": self.color_fps,
            "depth_width": self.depth_width, "depth_height": self.depth_height,
            "depth_fps": self.depth_fps,
            "ir_width": self.ir_width, "ir_height": self.ir_height,
            "ir_fps": self.ir_fps,
            "firmware_version": self.firmware_version,
            "hardware_version": self.hardware_version,
            "pid": self.pid, "vid": self.vid,
            "connection_type": self.connection_type,
        }


# ---------------------------------------------------------------------------
# 深度渲染
# ---------------------------------------------------------------------------

def _render_depth_3d(depth_mm: np.ndarray) -> np.ndarray:
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
    return (depth_colored * lighting[..., np.newaxis]).astype(np.uint8)


def _frame_to_jpeg_base64(frame: np.ndarray) -> str:
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(jpeg.tobytes()).decode("ascii")


# ---------------------------------------------------------------------------
# 相机管理器
# ---------------------------------------------------------------------------

class CameraManager:
    """管理多个奥比中光相机。"""

    def __init__(self, config_path: str):
        self._cameras: dict[str, CameraInfo] = {}
        self._pipelines: dict[str, Any] = {}
        self._streaming: dict[str, bool] = {}
        self._lock = threading.Lock()
        self._color_frames: dict[str, Optional[np.ndarray]] = {}
        self._depth_frames: dict[str, Optional[np.ndarray]] = {}
        self._ir_frames: dict[str, Optional[np.ndarray]] = {}
        self._frame_timestamps: dict[str, float] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._running = True
        self._ws_subscribers: dict[str, set] = {}  # camera_id -> set of ws
        self._init_cameras(config_path)

    def _init_cameras(self, config_path: str):
        from pyorbbecsdk import Context, OBLogLevel
        import yaml

        with open(config_path) as f:
            data = yaml.safe_load(f)
        configs = data.get("cameras", [])

        ctx = Context()
        ctx.set_logger_level(OBLogLevel.INFO)
        device_list = ctx.query_devices()

        logger.info("_init_cameras: config has %d cameras, SDK found %d devices",
                    len(configs), device_list.get_count())

        devices_by_serial = {}
        for i in range(device_list.get_count()):
            d = device_list.get_device_by_index(i)
            s = d.get_device_info().get_serial_number()
            logger.info("  device[%d]: serial='%s' name='%s'",
                        i, s, d.get_device_info().get_name())
            if s:
                devices_by_serial[s] = d
        logger.info("  serial index: %s", list(devices_by_serial.keys()))

        for cfg in configs:
            cid = cfg["id"]
            cfg_serial = cfg.get("serial", "")
            info = CameraInfo(
                id=cid, name=cfg.get("name", cid),
                serial=cfg_serial, usb_port=cfg.get("usb_port", ""),
                position=cfg.get("position", ""),
            )
            device = None
            if cfg_serial and cfg_serial in devices_by_serial:
                device = devices_by_serial[cfg_serial]
                logger.info("  camera '%s': serial '%s' MATCHED device", cid, cfg_serial)
            elif cfg_serial:
                logger.warning("  camera '%s': serial '%s' NOT in detected devices %s",
                               cid, cfg_serial, list(devices_by_serial.keys()))
            else:
                logger.warning("  camera '%s': no serial configured, skipping", cid)

            if device:
                di = device.get_device_info()
                info.connected = True
                info.serial = di.get_serial_number()
                info.firmware_version = di.get_firmware_version()
                info.hardware_version = di.get_hardware_version()
                info.pid = di.get_pid()
                info.vid = di.get_vid()
                info.connection_type = di.get_connection_type()

                from pyorbbecsdk import OBSensorType, Pipeline
                pipeline = Pipeline(device)
                self._pipelines[cid] = pipeline
                try:
                    cp = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR).get_default_video_stream_profile()
                    info.color_width, info.color_height, info.color_fps = cp.get_width(), cp.get_height(), cp.get_fps()
                except Exception:
                    pass
                try:
                    dp = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR).get_default_video_stream_profile()
                    info.depth_width, info.depth_height, info.depth_fps = dp.get_width(), dp.get_height(), dp.get_fps()
                except Exception:
                    pass
                try:
                    ir_profiles = pipeline.get_stream_profile_list(OBSensorType.IR_SENSOR)
                    ir_profile = ir_profiles.get_default_video_stream_profile()
                    info.ir_width, info.ir_height, info.ir_fps = ir_profile.get_width(), ir_profile.get_height(), ir_profile.get_fps()
                except Exception:
                    try:
                        ir_profiles = pipeline.get_stream_profile_list(OBSensorType.LEFT_IR_SENSOR)
                        ir_profile = ir_profiles.get_default_video_stream_profile()
                        info.ir_width, info.ir_height, info.ir_fps = ir_profile.get_width(), ir_profile.get_height(), ir_profile.get_fps()
                    except Exception:
                        pass

                cc = cfg.get("color_stream", {})
                if "width" in cc: info.color_width = cc["width"]
                if "height" in cc: info.color_height = cc["height"]
                if "fps" in cc: info.color_fps = cc["fps"]
                dc = cfg.get("depth_stream", {})
                if "width" in dc: info.depth_width = dc["width"]
                if "height" in dc: info.depth_height = dc["height"]
                if "fps" in dc: info.depth_fps = dc["fps"]

                logger.info("Camera '%s': %s %dx%d@%d", cid, info.serial,
                            info.color_width, info.color_height, info.color_fps)
            else:
                logger.warning("Camera '%s' not found", cid)

            self._cameras[cid] = info
            self._streaming[cid] = False
            self._color_frames[cid] = None
            self._depth_frames[cid] = None
            self._ir_frames[cid] = None
            self._frame_timestamps[cid] = 0.0
            self._ws_subscribers[cid] = set()

    # ---- 公共 API ----

    def get_camera_list(self) -> list[dict]:
        # 只返回实际连接的相机
        return [i.to_dict() for i in self._cameras.values() if i.connected]

    def start_stream(self, camera_id: str) -> dict:
        if camera_id not in self._cameras:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}
        if not self._cameras[camera_id].connected:
            return {"success": False, "message": f"Not connected: {camera_id}"}
        if self._streaming[camera_id]:
            return {"success": True, "message": f"Already streaming: {camera_id}"}

        pipeline = self._pipelines.get(camera_id)
        if pipeline is None:
            return {"success": False, "message": f"No pipeline: {camera_id}"}

        from pyorbbecsdk import Config, OBSensorType, OBError
        config = Config()
        try:
            config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR).get_default_video_stream_profile())
        except OBError:
            pass
        try:
            config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR).get_default_video_stream_profile())
        except OBError:
            pass
        try:
            config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.IR_SENSOR).get_default_video_stream_profile())
        except OBError:
            try:
                config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.LEFT_IR_SENSOR).get_default_video_stream_profile())
            except OBError:
                pass
        try:
            pipeline.start(config)
        except OBError as e:
            return {"success": False, "message": f"Pipeline start failed: {e}"}

        self._streaming[camera_id] = True
        t = threading.Thread(target=self._capture_loop, args=(camera_id,), daemon=True)
        self._threads[camera_id] = t
        t.start()
        logger.info("Stream started: %s", camera_id)
        return {"success": True, "message": f"Streaming {camera_id}"}

    def stop_stream(self, camera_id: str) -> dict:
        if camera_id not in self._cameras:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}
        self._streaming[camera_id] = False
        t = self._threads.pop(camera_id, None)
        if t and t.is_alive():
            t.join(timeout=2.0)
        p = self._pipelines.get(camera_id)
        if p:
            try: p.stop()
            except Exception: pass
        with self._lock:
            self._color_frames[camera_id] = None
            self._depth_frames[camera_id] = None
            self._ir_frames[camera_id] = None
        logger.info("Stream stopped: %s", camera_id)
        return {"success": True, "message": f"Stopped {camera_id}"}

    # ---- 帧获取 ----

    def get_latest_color(self, camera_id: str) -> Optional[np.ndarray]:
        with self._lock:
            f = self._color_frames.get(camera_id)
            return f.copy() if f is not None else None

    def get_latest_depth(self, camera_id: str) -> Optional[np.ndarray]:
        with self._lock:
            f = self._depth_frames.get(camera_id)
            return f.copy() if f is not None else None

    def get_latest_ir(self, camera_id: str) -> Optional[np.ndarray]:
        with self._lock:
            f = self._ir_frames.get(camera_id)
            return f.copy() if f is not None else None

    def get_frame_timestamp(self, camera_id: str) -> float:
        with self._lock:
            return self._frame_timestamps.get(camera_id, 0.0)

    def is_streaming(self, camera_id: str) -> bool:
        return self._streaming.get(camera_id, False)

    # ---- WS 订阅 ----

    def ws_subscribe(self, camera_id: str, ws):
        self._ws_subscribers[camera_id].add(ws)

    def ws_unsubscribe(self, camera_id: str, ws):
        self._ws_subscribers[camera_id].discard(ws)

    def _broadcast_frame(self, camera_id: str, data: dict):
        dead = set()
        for ws in self._ws_subscribers.get(camera_id, set()):
            try:
                ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._ws_subscribers[camera_id].discard(ws)

    # ---- 采集线程 ----

    def _capture_loop(self, camera_id: str):
        pipeline = self._pipelines[camera_id]
        fps = max(self._cameras[camera_id].color_fps, 15)
        interval = 1.0 / fps

        while self._running and self._streaming.get(camera_id, False):
            try:
                frames = pipeline.wait_for_frames(100)
                if frames is None:
                    time.sleep(0.01)
                    continue
                cf = frames.get_color_frame()
                df = frames.get_depth_frame()
                irf = frames.get_ir_frame()
                if irf is None:
                    irf = frames.get_left_ir_frame() if hasattr(frames, "get_left_ir_frame") else None
                with self._lock:
                    if cf is not None:
                        self._color_frames[camera_id] = self._to_bgr(cf)
                    if df is not None:
                        self._depth_frames[camera_id] = self._to_depth_mm(df)
                    if irf is not None:
                        self._ir_frames[camera_id] = self._to_ir_gray(irf)
                    self._frame_timestamps[camera_id] = time.time()
            except Exception:
                logger.exception("Capture error: %s", camera_id)
            time.sleep(interval)

    @staticmethod
    def _to_bgr(frame) -> Optional[np.ndarray]:
        from pyorbbecsdk import OBFormat
        w, h, fmt = frame.get_width(), frame.get_height(), frame.get_format()
        data = np.asanyarray(frame.get_data())
        if fmt == OBFormat.RGB:
            return cv2.cvtColor(data.reshape((h, w, 3)), cv2.COLOR_RGB2BGR)
        elif fmt == OBFormat.BGR:
            return data.reshape((h, w, 3))
        elif fmt == OBFormat.YUYV:
            return cv2.cvtColor(data.reshape((h, w, 2)), cv2.COLOR_YUV2BGR_YUYV)
        elif fmt == OBFormat.MJPG:
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
        elif fmt == OBFormat.I420:
            y = data[:h, :]
            u = data[h:h + h // 4].reshape(h // 2, w // 2)
            v = data[h + h // 4:].reshape(h // 2, w // 2)
            return cv2.cvtColor(cv2.merge([y, u, v]), cv2.COLOR_YUV2BGR_I420)
        elif fmt == OBFormat.NV12:
            y = data[:h, :]
            uv = data[h:h + h // 2].reshape(h // 2, w)
            return cv2.cvtColor(cv2.merge([y, uv]), cv2.COLOR_YUV2BGR_NV12)
        elif fmt == OBFormat.NV21:
            y = data[:h, :]
            uv = data[h:h + h // 2].reshape(h // 2, w)
            return cv2.cvtColor(cv2.merge([y, uv]), cv2.COLOR_YUV2BGR_NV21)
        elif fmt == OBFormat.UYVY:
            return cv2.cvtColor(data.reshape((h, w, 2)), cv2.COLOR_YUV2BGR_UYVY)
        return None

    @staticmethod
    def _to_depth_mm(frame) -> np.ndarray:
        w, h = frame.get_width(), frame.get_height()
        scale = frame.get_depth_scale()
        raw = np.frombuffer(frame.get_data(), dtype=np.uint16)
        return raw.reshape((h, w)).astype(np.float32) * scale

    @staticmethod
    def _to_ir_gray(frame) -> Optional[np.ndarray]:
        """IR 帧 → uint8 灰度图 (复用 test_ir_chessboard.py 已验证逻辑)。"""
        from pyorbbecsdk import OBFormat
        w, h, fmt = frame.get_width(), frame.get_height(), frame.get_format()
        raw = np.frombuffer(frame.get_data(), dtype=np.uint8)

        if fmt == OBFormat.Y8:
            return raw.reshape((h, w)).copy()
        elif fmt in (OBFormat.Y16, OBFormat.YUYV, OBFormat.YUY2):
            raw_u16 = raw.view(np.uint16).reshape((h, w))
            try:
                bit_size = frame.pixel_available_bit_size()
            except Exception:
                bit_size = 16
            scale = 1.0 / (2 ** (bit_size - 8)) if bit_size > 8 else 1.0
            return (raw_u16.astype(np.float32) * scale).clip(0, 255).astype(np.uint8)
        elif fmt == OBFormat.MJPG:
            return cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
        return None

    def shutdown(self):
        self._running = False
        for cid in list(self._streaming):
            if self._streaming[cid]:
                self.stop_stream(cid)


# ---------------------------------------------------------------------------
# WebSocket 推流服务器
# ---------------------------------------------------------------------------

try:
    import websockets
    HAS_WS = True
except ImportError:
    HAS_WS = False


class _WsProtocol:
    """简易 WebSocket 协议处理器（不依赖 websockets 包，使用 asyncio 原生）。"""

    def __init__(self, manager: CameraManager):
        self._manager = manager

    async def handle(self, ws):
        camera_id = None
        stream_type = "raw"
        push_task = None

        async def push_loop():
            last_ts = 0.0
            fps = 15
            if camera_id:
                for c in self._manager.get_camera_list():
                    if c["id"] == camera_id:
                        fps = max(c.get("color_fps", 15), 15)
                        break
            interval = 1.0 / fps

            while True:
                try:
                    if camera_id is None:
                        await asyncio.sleep(0.1)
                        continue
                    ts = self._manager.get_frame_timestamp(camera_id)
                    if ts == last_ts:
                        await asyncio.sleep(0.01)
                        continue
                    last_ts = ts

                    if stream_type == "depth":
                        frame = self._manager.get_latest_depth(camera_id)
                        if frame is not None:
                            frame = _render_depth_3d(frame)
                    elif stream_type == "ir":
                        frame = self._manager.get_latest_ir(camera_id)
                    elif stream_type == "annotated":
                        frame = self._manager.get_latest_color(camera_id)
                        if frame is not None:
                            try:
                                # Try to get or create detector for this camera
                                detector = None
                                if hasattr(self._manager, '_qr_detectors') and camera_id in self._manager._qr_detectors:
                                    detector = self._manager._qr_detectors[camera_id]
                                elif hasattr(self._manager, '_qr_detector') and self._manager._qr_detector is not None:
                                    detector = self._manager._qr_detector

                                if detector is not None:
                                    results = detector.detect(frame, 0.058)
                                    frame = detector.draw_results(frame, results)
                            except Exception:
                                logger.exception("annotated frame generation failed")
                    else:
                        frame = self._manager.get_latest_color(camera_id)

                    if frame is None:
                        await asyncio.sleep(0.01)
                        continue

                    jpeg_b64 = _frame_to_jpeg_base64(frame)
                    await ws.send(json.dumps({
                        "type": "frame", "camera_id": camera_id,
                        "stream_type": stream_type, "data": jpeg_b64,
                    }))
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(0.1)

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                action = msg.get("action", "")
                if action == "subscribe":
                    camera_id = msg.get("camera_id", "")
                    stream_type = msg.get("stream_type", "raw")
                    cam_list = [c["id"] for c in self._manager.get_camera_list()]
                    if camera_id not in cam_list:
                        await ws.send(json.dumps({"type": "error", "message": f"Camera not found: {camera_id}"}))
                        continue
                    if not self._manager.is_streaming(camera_id):
                        self._manager.start_stream(camera_id)
                    if push_task:
                        push_task.cancel()
                    push_task = asyncio.create_task(push_loop())
                    logger.info("WS subscribe: %s/%s", camera_id, stream_type)
                elif action == "unsubscribe":
                    if push_task:
                        push_task.cancel()
                        push_task = None
                    camera_id = None
                else:
                    await ws.send(json.dumps({"type": "error", "message": f"Unknown action: {action}"}))
        except Exception:
            pass
        finally:
            if push_task:
                push_task.cancel()


async def _run_ws_server(manager: CameraManager):
    """启动 WebSocket 服务器。"""
    try:
        import websockets as ws_lib
        proto = _WsProtocol(manager)

        async def handler(websocket):
            await proto.handle(websocket)

        async with ws_lib.serve(handler, WS_HOST, WS_PORT):
            logger.info("WS server listening on %s:%d", WS_HOST, WS_PORT)
            await asyncio.Future()  # run forever
    except ImportError:
        # fallback: use aiohttp or just log warning
        logger.warning("websockets package not installed. Install: pip install websockets")
        logger.warning("WS server NOT started. Video streaming unavailable.")


def _run_ws_in_thread(manager: CameraManager):
    """在独立线程中运行 asyncio event loop 驱动 WS server。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_ws_server(manager))
    except Exception:
        logger.exception("WS server crashed")


# ---------------------------------------------------------------------------
# ROS2 Node
# ---------------------------------------------------------------------------

def main(args=None):
    import rclpy
    from rclpy.node import Node
    from furance_interfaces.srv import GenericCommand

    rclpy.init(args=args)
    node = Node("camera_manager")
    logger.info("CameraManager node starting...")

    config_path = os.environ.get("CAMERA_CONFIG_PATH", "")
    if not config_path:
        from ament_index_python.packages import get_package_share_directory
        config_path = os.path.join(get_package_share_directory("python_pkgs"), "orbbec_vision", "camera_config.yaml")
    manager = CameraManager(config_path)

    # ---- Vision modules ----
    import yaml as _yaml
    _config_dir = os.path.dirname(config_path)
    _scenes_dir = os.path.join(_config_dir, "scenes")
    _scene_manager = None
    _qr_calibrator = None

    # 加载相机配置供 QRCalibrator 使用
    with open(config_path) as _f:
        _cam_configs = {c["id"]: c for c in _yaml.safe_load(_f).get("cameras", [])}

    try:
        from python_pkgs.orbbec_vision.scene_manager import SceneManager
        _scene_manager = SceneManager(_scenes_dir)
        logger.info("SceneManager initialized")
    except Exception:
        logger.exception("Failed to init SceneManager")

    try:
        from python_pkgs.orbbec_vision.qr_calibrator import QRCalibrator
        _qr_calibrator = QRCalibrator(_scene_manager, _cam_configs)
        logger.info("QRCalibrator initialized")
    except Exception:
        logger.exception("Failed to init QRCalibrator")

    # QRDetector for annotated stream (lazy per camera)
    _qr_detectors: dict[str, object] = {}

    # Attach a default QRDetector to manager for annotated stream
    try:
        from python_pkgs.orbbec_vision.qr_detector import QRDetector
        # Create a dummy detector (will be replaced per camera if needed)
        # Note: Real usage should create detector with proper intrinsics
        manager._qr_detectors = _qr_detectors  # Store dict on manager
        # Also provide a default detector for backward compatibility
        dummy_K = np.eye(3, dtype=np.float64)
        dummy_D = np.zeros(5, dtype=np.float64)
        manager._qr_detector = QRDetector(dummy_K, dummy_D)
    except Exception:
        logger.exception("Failed to create default QRDetector")
        manager._qr_detector = None
        manager._qr_detectors = {}

    # 启动 WS server 线程
    ws_thread = threading.Thread(target=_run_ws_in_thread, args=(manager,), daemon=True)
    ws_thread.start()

    # ---- ROS2 Services ----

    def _handle_list(request, response):
        response.success = True
        response.message = "OK"
        response.result_json = json.dumps(manager.get_camera_list())
        return response

    def _handle_stream_start(request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        camera_id = params.get("camera_id", "")
        result = manager.start_stream(camera_id)
        response.success = result["success"]
        response.message = result["message"]
        response.result_json = "{}"
        return response

    def _handle_stream_stop(request, response):
        params = json.loads(request.params_json) if request.params_json else {}
        camera_id = params.get("camera_id", "")
        result = manager.stop_stream(camera_id)
        response.success = result["success"]
        response.message = result["message"]
        response.result_json = "{}"
        return response

    node.create_service(GenericCommand, "/camera/list", _handle_list)
    node.create_service(GenericCommand, "/camera/stream/start", _handle_stream_start)
    node.create_service(GenericCommand, "/camera/stream/stop", _handle_stream_stop)

    # /camera/calibrate
    from control_interfaces.srv import QRCalibrate

    def _handle_calibrate(request, response):
        if _qr_calibrator is None:
            response.success = False
            response.message = "QRCalibrator not available"
            return response
        # Get latest frame from the requested camera
        color_frame = manager.get_latest_color(request.camera_id)
        ir_frame = manager.get_latest_ir(request.camera_id)
        result = _qr_calibrator.calibrate(
            camera_id=request.camera_id,
            arm=request.arm,
            qr_id=request.qr_id,
            marker_size=request.marker_size,
            point_name=request.point_name,
            scene_id=request.scene_id,
            color_frame=color_frame,
            ir_frame=ir_frame,
        )
        response.success = result["success"]
        response.message = result["message"]
        if result["success"]:
            response.translation = result["translation"]
            response.rotation = result["rotation"]
        return response

    node.create_service(QRCalibrate, "/camera/calibrate", _handle_calibrate)

    # /camera/scene
    from control_interfaces.srv import SceneOperation

    def _handle_scene(request, response):
        if _scene_manager is None:
            response.success = False
            response.message = "SceneManager not available"
            return response
        import json as _json
        params = _json.loads(request.params_json) if request.params_json else {}
        action = request.action
        scene_id = request.scene_id
        try:
            if action == "list":
                result = _scene_manager.list_scenes()
                response.success = True
                response.result_json = _json.dumps(result)
            elif action == "get":
                data = _scene_manager.get_scene(scene_id)
                if data is None:
                    response.success = False
                    response.message = f"Scene not found: {scene_id}"
                else:
                    response.success = True
                    response.result_json = _json.dumps(data)
            elif action == "create":
                ok = _scene_manager.create_scene(scene_id, params.get("description", ""))
                response.success = ok
                response.message = "Created" if ok else f"Already exists: {scene_id}"
            elif action == "delete":
                ok = _scene_manager.delete_scene(scene_id)
                response.success = ok
                response.message = "Deleted" if ok else f"Not found: {scene_id}"
            elif action == "add_point":
                ok = _scene_manager.add_point(
                    scene_id=scene_id,
                    qr_id=params.get("qr_id", 0),
                    name=params.get("name", ""),
                    arm=params.get("arm", "right"),
                    marker_size=params.get("marker_size", 0.058),
                    T_qr_workspace=params.get("T_qr_workspace", {}),
                )
                response.success = ok
                response.message = "Point added" if ok else "Failed"
            elif action == "delete_point":
                ok = _scene_manager.delete_point(scene_id, params.get("name", ""))
                response.success = ok
                response.message = "Point deleted" if ok else "Not found"
            elif action == "update_point":
                update_kwargs = {k: v for k, v in params.items() if k != "name"}
                ok = _scene_manager.update_point(scene_id, params.get("name", ""), **update_kwargs)
                response.success = ok
                response.message = "Updated" if ok else "Not found"
            else:
                response.success = False
                response.message = f"Unknown action: {action}"
        except Exception as e:
            logger.exception("Scene operation failed: %s", action)
            response.success = False
            response.message = str(e)
        return response

    node.create_service(SceneOperation, "/camera/scene", _handle_scene)

    # /camera/compute_pose
    from control_interfaces.srv import ComputePose

    def _handle_compute_pose(request, response):
        if _scene_manager is None:
            response.success = False
            response.message = "SceneManager not available"
            return response
        try:
            # 1. Get scene point
            point = _scene_manager.find_point(request.scene_id, request.point_name)
            if point is None:
                response.success = False
                response.message = f"Point not found: {request.scene_id}/{request.point_name}"
                return response

            T_qr_ws = point.get("T_qr_workspace", {})
            t_ws = T_qr_ws.get("translation", [0, 0, 0])
            r_ws = T_qr_ws.get("rotation", [0, 0, 0, 1])

            # 2. Get camera intrinsics for QR detection
            cfg = _cam_configs.get(request.camera_id, {})
            calib = cfg.get("calibration", {})
            intrinsics = calib.get("color_intrinsics", {})

            if not intrinsics.get("fx"):
                response.success = False
                response.message = f"No intrinsics for camera: {request.camera_id}"
                return response

            # 3. Detect QR from latest frame
            from python_pkgs.orbbec_vision.qr_detector import QRDetector
            import numpy as np

            K = np.array([
                [intrinsics["fx"], 0, intrinsics["cx"]],
                [0, intrinsics["fy"], intrinsics["cy"]],
                [0, 0, 1],
            ], dtype=np.float64)
            D = np.array(intrinsics.get("distortion", [0, 0, 0, 0, 0]), dtype=np.float64)
            detector = QRDetector(K, D)

            color_frame = manager.get_latest_color(request.camera_id)
            ir_frame = manager.get_latest_ir(request.camera_id)
            frame = color_frame if color_frame is not None else ir_frame
            if frame is None:
                response.success = False
                response.message = "No frame available"
                return response

            marker_size = point.get("marker_size", 0.058)
            qr_id = point.get("qr_id", 0)
            results = detector.detect(frame, marker_size)
            qr_result = next((r for r in results if r.qr_id == qr_id), None)
            if qr_result is None:
                response.success = False
                response.message = f"QR id={qr_id} not found"
                return response

            # 4. T_camera_qr
            import cv2 as _cv2
            R_cam_qr, _ = _cv2.Rodrigues(qr_result.rvec)
            T_cam_qr = np.eye(4)
            T_cam_qr[:3, :3] = R_cam_qr
            T_cam_qr[:3, 3] = qr_result.tvec.ravel()

            # 5. T_qr_workspace from scene
            # Rotation is stored as quaternion [x,y,z,w]
            qx, qy, qz, qw = r_ws
            R_ws = np.array([
                [1 - 2*qy*qy - 2*qz*qz, 2*qx*qy - 2*qz*qw, 2*qx*qz + 2*qy*qw],
                [2*qx*qy + 2*qz*qw, 1 - 2*qx*qx - 2*qz*qz, 2*qy*qz - 2*qx*qw],
                [2*qx*qz - 2*qy*qw, 2*qy*qz + 2*qx*qw, 1 - 2*qx*qx - 2*qy*qy],
            ])
            T_qr_ws = np.eye(4)
            T_qr_ws[:3, :3] = R_ws
            T_qr_ws[:3, 3] = t_ws

            # 6. T_camera_ws = T_camera_qr * T_qr_workspace
            T_cam_ws = T_cam_qr @ T_qr_ws

            # 7. Get T_camera_ee from config
            arm = point.get("arm", "right")
            ee_link = f"ARM-{arm.upper()}-J7_Link"
            cam_to_ee = calib.get(f"camera_to_{ee_link}", {})
            if not cam_to_ee.get("translation"):
                response.success = False
                response.message = f"No camera_to_ee calibration for {ee_link}"
                return response
            R_cam_ee, _ = _cv2.Rodrigues(np.array(cam_to_ee["rotation"], dtype=np.float64))
            T_cam_ee = np.eye(4)
            T_cam_ee[:3, :3] = R_cam_ee
            # Convert translation from mm to meters if needed
            t = cam_to_ee["translation"]
            T_cam_ee[:3, 3] = [
                float(t[0]) / 1000.0 if abs(t[0]) > 10 else float(t[0]),
                float(t[1]) / 1000.0 if abs(t[1]) > 10 else float(t[1]),
                float(t[2]) / 1000.0 if abs(t[2]) > 10 else float(t[2]),
            ]

            # 8. T_ee_ws = inv(T_camera_ee) * T_camera_ws
            T_ee_ws = np.linalg.inv(T_cam_ee) @ T_cam_ws

            # 9. Extract xyzrpy (rotation matrix → euler xyz)
            x, y, z = float(T_ee_ws[0, 3]), float(T_ee_ws[1, 3]), float(T_ee_ws[2, 3])
            R_ee = T_ee_ws[:3, :3]
            # Pure numpy: rotation matrix → euler angles (xyz convention)
            sy = np.sqrt(R_ee[0, 0] ** 2 + R_ee[1, 0] ** 2)
            singular = sy < 1e-6
            if not singular:
                roll = float(np.arctan2(R_ee[2, 1], R_ee[2, 2]))
                pitch = float(np.arctan2(-R_ee[2, 0], sy))
                yaw = float(np.arctan2(R_ee[1, 0], R_ee[0, 0]))
            else:
                roll = float(np.arctan2(-R_ee[1, 2], R_ee[1, 1]))
                pitch = float(np.arctan2(-R_ee[2, 0], sy))
                yaw = 0.0

            response.success = True
            response.message = "Computed"
            response.x = x
            response.y = y
            response.z = z
            response.roll = roll
            response.pitch = pitch
            response.yaw = yaw

            logger.info("compute_pose: camera=%s scene=%s point=%s → xyz=[%.4f,%.4f,%.4f] rpy=[%.4f,%.4f,%.4f]",
                        request.camera_id, request.scene_id, request.point_name,
                        x, y, z, roll, pitch, yaw)
        except Exception as e:
            logger.exception("compute_pose failed")
            response.success = False
            response.message = str(e)
        return response

    node.create_service(ComputePose, "/camera/compute_pose", _handle_compute_pose)

    # ---- TF Broadcaster for camera→ee transforms ----
    import tf2_ros
    _tf_broadcaster = tf2_ros.TransformBroadcaster(node)
    _tf_timer = None

    def _publish_calibration_tfs():
        """读取 config 中的 camera_to_<ee_link> 并发布静态 TF。"""
        for cid, cfg in _cam_configs.items():
            try:
                calib = cfg.get("calibration", {})
                for key, transform in calib.items():
                    if not key.startswith("camera_to_"):
                        continue
                    ee_link = key[len("camera_to_"):]
                    t = transform.get("translation", [0, 0, 0])
                    r = transform.get("rotation", [0, 0, 0])
                    # rotation is stored as rodrigues vector
                    import cv2 as _cv2
                    R_mat, _ = _cv2.Rodrigues(np.array(r, dtype=np.float64))
                    # matrix → quaternion
                    from geometry_msgs.msg import TransformStamped
                    _tf_msg = TransformStamped()
                    _tf_msg.header.stamp = node.get_clock().now().to_msg()
                    _tf_msg.header.frame_id = cid + "_link" if not cid.endswith("_link") else cid
                    _tf_msg.child_frame_id = ee_link
                    _tf_msg.transform.translation.x = float(t[0]) / 1000.0 if abs(t[0]) > 10 else float(t[0])
                    _tf_msg.transform.translation.y = float(t[1]) / 1000.0 if abs(t[1]) > 10 else float(t[1])
                    _tf_msg.transform.translation.z = float(t[2]) / 1000.0 if abs(t[2]) > 10 else float(t[2])
                    # rotation matrix → quaternion
                    tr = np.trace(R_mat)
                    if tr > 0:
                        S = np.sqrt(tr + 1.0) * 2
                        qw = 0.25 * S
                        qx = (R_mat[2, 1] - R_mat[1, 2]) / S
                        qy = (R_mat[0, 2] - R_mat[2, 0]) / S
                        qz = (R_mat[1, 0] - R_mat[0, 1]) / S
                    elif R_mat[0, 0] > R_mat[1, 1] and R_mat[0, 0] > R_mat[2, 2]:
                        S = np.sqrt(1.0 + R_mat[0, 0] - R_mat[1, 1] - R_mat[2, 2]) * 2
                        qw = (R_mat[2, 1] - R_mat[1, 2]) / S
                        qx = 0.25 * S
                        qy = (R_mat[0, 1] + R_mat[1, 0]) / S
                        qz = (R_mat[0, 2] + R_mat[2, 0]) / S
                    elif R_mat[1, 1] > R_mat[2, 2]:
                        S = np.sqrt(1.0 + R_mat[1, 1] - R_mat[0, 0] - R_mat[2, 2]) * 2
                        qw = (R_mat[0, 2] - R_mat[2, 0]) / S
                        qx = (R_mat[0, 1] + R_mat[1, 0]) / S
                        qy = 0.25 * S
                        qz = (R_mat[1, 2] + R_mat[2, 1]) / S
                    else:
                        S = np.sqrt(1.0 + R_mat[2, 2] - R_mat[0, 0] - R_mat[1, 1]) * 2
                        qw = (R_mat[1, 0] - R_mat[0, 1]) / S
                        qx = (R_mat[0, 2] + R_mat[2, 0]) / S
                        qy = (R_mat[1, 2] + R_mat[2, 1]) / S
                        qz = 0.25 * S
                    _tf_msg.transform.rotation.x = float(qx)
                    _tf_msg.transform.rotation.y = float(qy)
                    _tf_msg.transform.rotation.z = float(qz)
                    _tf_msg.transform.rotation.w = float(qw)
                    _tf_broadcaster.sendTransform(_tf_msg)
                    logger.debug("TF: %s → %s published", _tf_msg.header.frame_id, ee_link)
            except Exception:
                logger.exception("TF publish failed for camera '%s'", cid)

    _tf_timer = node.create_timer(1.0, _publish_calibration_tfs)
    logger.info("TF broadcaster started for camera→ee transforms")

    logger.info("CameraManager node ready (WS %s:%d)", WS_HOST, WS_PORT)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

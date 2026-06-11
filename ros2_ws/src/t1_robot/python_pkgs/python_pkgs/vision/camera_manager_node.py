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
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

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

_DEFAULT_CONFIG = Path(__file__).resolve().parent / "camera_config.yaml"


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
        ctx.set_logger_level(OBLogLevel.WARNING)
        device_list = ctx.query_devices()

        devices_by_serial = {}
        for i in range(device_list.get_count()):
            d = device_list.get_device_by_index(i)
            s = d.get_device_info().get_serial_number()
            if s:
                devices_by_serial[s] = d

        for cfg in configs:
            cid = cfg["id"]
            info = CameraInfo(
                id=cid, name=cfg.get("name", cid),
                serial=cfg.get("serial", ""), usb_port=cfg.get("usb_port", ""),
                position=cfg.get("position", ""),
            )
            device = None
            if info.serial and info.serial in devices_by_serial:
                device = devices_by_serial[info.serial]

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
            self._frame_timestamps[cid] = 0.0
            self._ws_subscribers[cid] = set()

    # ---- 公共 API ----

    def get_camera_list(self) -> list[dict]:
        return [i.to_dict() for i in self._cameras.values()]

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
                with self._lock:
                    if cf is not None:
                        self._color_frames[camera_id] = self._to_bgr(cf)
                    if df is not None:
                        self._depth_frames[camera_id] = self._to_depth_mm(df)
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

    config_path = os.environ.get("CAMERA_CONFIG_PATH", str(_DEFAULT_CONFIG))
    manager = CameraManager(config_path)

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

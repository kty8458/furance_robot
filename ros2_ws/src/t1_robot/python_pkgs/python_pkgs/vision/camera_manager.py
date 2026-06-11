#!/usr/bin/env python3
"""
相机管理器 — 基于 pyorbbecsdk 直连奥比中光相机。

功能:
  - 读取 camera_config.yaml，按 serial/usb_port 匹配物理相机
  - 为每个相机管理 pyorbbecsdk.Pipeline 实例
  - 后台线程持续采集帧，缓存最新一帧
  - 提供同步 getter 方法供视觉算法和 WebSocket 推流使用

用法:
  from python_pkgs.vision.camera_manager import init_camera_manager, get_camera_manager

  # 在 robot_control 启动时初始化
  init_camera_manager(config_path)

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
from dataclasses import dataclass
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
        logger.warning(
            "pyorbbecsdk lib dir not in LD_LIBRARY_PATH. "
            "Set before starting server: "
            "export LD_LIBRARY_PATH=%s:$LD_LIBRARY_PATH",
            _SDK_LIB_DIR,
        )

import cv2

# 全局单例
_camera_manager: Optional["CameraManager"] = None


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


class CameraManager:
    """管理多个奥比中光相机，提供帧缓存和同步获取接口。"""

    def __init__(self, config_path: str):
        self._config_path = config_path
        self._cameras: dict[str, CameraInfo] = {}
        self._pipelines: dict[str, Any] = {}
        self._streaming: dict[str, bool] = {}

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

        # 构建设备查找表: serial -> device
        devices_by_serial: dict[str, Any] = {}
        for i in range(device_list.get_count()):
            device = device_list.get_device_by_index(i)
            info = device.get_device_info()
            serial = info.get_serial_number()
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

    # ---- 后台采集 ----

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

    # ---- 同步帧获取 ----

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


# ---- 模块级单例管理 ----

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

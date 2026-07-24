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
# 配置 orbbec_vision 命名空间下所有 logger 输出到 stderr
_ov = logging.getLogger("orbbec_vision")
if not _ov.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[%(name)s %(levelname)s] %(message)s"))
    _ov.addHandler(_h)
    _ov.setLevel(logging.INFO)
    _ov.propagate = False

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

def _rotmat_to_euler(R: np.ndarray) -> tuple[float, float, float]:
    """旋转矩阵 → xyz 欧拉角 (roll, pitch, yaw) 度, 纯 numpy"""
    sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        roll = np.arctan2(R[2, 1], R[2, 2])
        pitch = np.arctan2(-R[2, 0], sy)
        yaw = np.arctan2(R[1, 0], R[0, 0])
    else:
        roll = np.arctan2(-R[1, 2], R[1, 1])
        pitch = np.arctan2(-R[2, 0], sy)
        yaw = 0.0
    return (float(np.degrees(roll)), float(np.degrees(pitch)), float(np.degrees(yaw)))


class PoseStabilityTracker:
    """滑动窗口位姿稳定性统计。

    指标 (叠加在 annotated 推流画面上):
      t_std:  平移各轴标准差 (mm)
      t_ptp:  平移各轴峰峰值 (mm)
      r_std:  旋转各轴标准差 (deg)
      r_ptp:  旋转各轴峰峰值 (deg)
    """

    def __init__(self, window: int = 60):
        self._window = window
        self._tvecs: list[np.ndarray] = []
        self._rvecs: list[np.ndarray] = []  # 欧拉角 (deg)

    def push(self, tvec: np.ndarray, rvec: np.ndarray):
        self._tvecs.append(np.asarray(tvec).ravel().copy())
        r_flat = np.asarray(rvec).ravel()
        R, _ = cv2.Rodrigues(r_flat)
        euler = _rotmat_to_euler(R)
        self._rvecs.append(np.array(euler))
        while len(self._tvecs) > self._window:
            self._tvecs.pop(0)
            self._rvecs.pop(0)

    @property
    def ready(self) -> bool:
        return len(self._tvecs) >= 5

    @property
    def stats(self) -> dict:
        if len(self._tvecs) < 3:
            return {"samples": len(self._tvecs)}
        t = np.array(self._tvecs)
        r = np.array(self._rvecs)
        return {
            "samples": len(self._tvecs),
            "t_std": tuple(float(v) for v in np.std(t, axis=0) * 1000),
            "t_ptp": tuple(float(v) for v in (np.max(t, axis=0) - np.min(t, axis=0)) * 1000),
            "r_std": tuple(float(v) for v in np.std(r, axis=0)),
            "r_ptp": tuple(float(v) for v in (np.max(r, axis=0) - np.min(r, axis=0))),
        }

    def mean_tvec(self) -> np.ndarray | None:
        """返回滑窗内平移向量的均值 (3,) 单位: m，用于抑制单帧跳变。"""
        if len(self._tvecs) < 3:
            return None
        return np.mean(np.array(self._tvecs), axis=0)

    def mean_rvec(self) -> np.ndarray | None:
        """返回滑窗内旋转向量的均值 (3,) 单位: deg，用于抑制单帧跳变。"""
        if len(self._rvecs) < 3:
            return None
        return np.mean(np.array(self._rvecs), axis=0)

    def reset(self):
        self._tvecs.clear()
        self._rvecs.clear()


def _corner_area(corners: np.ndarray) -> float:
    """计算 QR 4 个角点构成的四边形像素面积 (作为检测置信度代理)."""
    pts = corners.reshape(-1, 2)
    if len(pts) < 4:
        return 0.0
    # Shoelace formula
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _mad_filter(values: np.ndarray, threshold: float = 3.0):
    """基于 MAD (中位数绝对偏差) 的离群剔除。

    Args:
        values: shape (N,) 或 (N, D)
        threshold: |x - median| / MAD > threshold 视为离群
    Returns:
        mask: shape (N,) 布尔数组, True 表示保留
    """
    if len(values) <= 2:
        return np.ones(len(values), dtype=bool)
    arr = np.asarray(values)
    if arr.ndim == 1:
        median = np.median(arr)
        mad = np.median(np.abs(arr - median)) + 1e-9
        return np.abs(arr - median) / mad < threshold
    # 多维: 用每点到中位数的欧氏距离做 MAD
    median = np.median(arr, axis=0)
    dists = np.linalg.norm(arr - median, axis=1)
    mad = np.median(np.abs(dists - np.median(dists))) + 1e-9
    return np.abs(dists - np.median(dists)) / mad < threshold


def _quat_weighted_mean(quats: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """加权四元数平均 (Markley 等论文方法: 对加权外积矩阵求最大特征向量)。

    Args:
        quats: shape (N, 4) 每行 [x, y, z, w]
        weights: shape (N,)
    Returns:
        归一化后的四元数 [x, y, z, w]
    """
    if len(quats) == 1:
        return quats[0] / np.linalg.norm(quats[0])
    # 处理四元数符号歧义: 使所有四元数与第一个同号
    qs = quats.copy()
    for i in range(1, len(qs)):
        if np.dot(qs[0], qs[i]) < 0:
            qs[i] = -qs[i]
    # 加权外积矩阵
    M = np.zeros((4, 4))
    for q, w in zip(qs, weights):
        M += w * np.outer(q, q)
    M /= np.sum(weights)
    # 最大特征值对应的特征向量
    eigvals, eigvecs = np.linalg.eigh(M)
    q_mean = eigvecs[:, -1]
    return q_mean / np.linalg.norm(q_mean)


def _annotate_frame(manager, camera_id: str, frame: np.ndarray) -> np.ndarray:
    """对帧进行 QR 检测 + 标注 + 多 QR 稳定性叠印 (供 annotated / ir_annotated 复用)。"""
    detector = None
    if hasattr(manager, '_qr_detectors') and camera_id in manager._qr_detectors:
        detector = manager._qr_detectors[camera_id]

    if detector is not None:
        results = detector.detect(frame, 0.058)
        frame = detector.draw_results(frame, results)

        # 多 QR 稳定性: 每个 QR 维护独立 tracker (按 qr_id key)
        if hasattr(manager, '_stability_trackers_per_id'):
            trackers = manager._stability_trackers_per_id.setdefault(camera_id, {})
            seen_ids = []
            for r in results:
                tr = trackers.setdefault(r.qr_id, PoseStabilityTracker(60))
                tr.push(r.tvec, r.rvec)
                seen_ids.append(r.qr_id)
            frame = _draw_multi_stability_overlay(frame, trackers, seen_ids)
    return frame


def _yolo_annotate_frame(manager, camera_id: str, frame: np.ndarray) -> np.ndarray:
    """YOLO 分割标注: 掩码半透明叠加 + 检测框 + 类名置信度 (供 mask 流复用)。

    模型未加载时返回原图 (优雅降级)。
    """
    detector = None
    if hasattr(manager, '_yolo_detectors') and camera_id in manager._yolo_detectors:
        detector = manager._yolo_detectors[camera_id]
    if detector is None:
        return frame
    try:
        results = detector.detect(frame)
        frame = detector.draw_results(frame, results)
    except Exception:
        logger.exception("yolo annotate frame failed: %s", camera_id)
    return frame


def _draw_multi_stability_overlay(frame: np.ndarray, trackers: dict, visible_ids: list) -> np.ndarray:
    """在画面左上角叠加多个 QR 的稳定性统计 (每个 QR 一组紧凑显示)。"""
    out = frame.copy()
    y_offset = 40
    for qid in sorted(visible_ids):
        tr = trackers.get(qid)
        if tr is None or not tr.ready:
            continue
        s = tr.stats
        header = f"ID={qid}  samples={s['samples']}"
        cv2.putText(out, header, (10, y_offset),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 220, 255), 2)
        y_offset += 32
        # 每行单独拆开避免过长
        lines = [
            f" t_std:[{s['t_std'][0]:.2f},{s['t_std'][1]:.2f},{s['t_std'][2]:.2f}]mm",
            f" t_ptp:[{s['t_ptp'][0]:.2f},{s['t_ptp'][1]:.2f},{s['t_ptp'][2]:.2f}]mm",
            f" r_std:[{s['r_std'][0]:.2f},{s['r_std'][1]:.2f},{s['r_std'][2]:.2f}]deg",
            f" r_ptp:[{s['r_ptp'][0]:.2f},{s['r_ptp'][1]:.2f},{s['r_ptp'][2]:.2f}]deg",
        ]
        for line in lines:
            cv2.putText(out, line, (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 50), 2)
            y_offset += 28
        y_offset += 8
    return out


def _draw_stability_overlay(frame: np.ndarray, tracker: PoseStabilityTracker) -> np.ndarray:
    """在 annotated 帧左上角叠加稳定性统计指标。"""
    if not tracker.ready:
        return frame
    s = tracker.stats
    out = frame.copy()
    lines = [
        f"t_std:[{s['t_std'][0]:.2f},{s['t_std'][1]:.2f},{s['t_std'][2]:.2f}]mm",
        f"t_ptp:[{s['t_ptp'][0]:.2f},{s['t_ptp'][1]:.2f},{s['t_ptp'][2]:.2f}]mm",
        f"r_std:[{s['r_std'][0]:.2f},{s['r_std'][1]:.2f},{s['r_std'][2]:.2f}]deg",
        f"r_ptp:[{s['r_ptp'][0]:.2f},{s['r_ptp'][1]:.2f},{s['r_ptp'][2]:.2f}]deg",
    ]
    for j, line in enumerate(lines):
        cv2.putText(out, line, (10, 80 + j * 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 200, 50), 2)
    return out

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
        self._devices: dict[str, Any] = {}  # 缓存设备对象，按需创建 pipeline
        self._streaming: dict[str, bool] = {}
        self._stream_types: dict[str, str] = {}  # camera_id -> stream_type
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
            try:
                d = device_list.get_device_by_index(i)
                s = d.get_device_info().get_serial_number()
                logger.info("  device[%d]: serial='%s' name='%s'",
                            i, s, d.get_device_info().get_name())
                if s:
                    devices_by_serial[s] = d
            except Exception as e:
                # 单个设备 UVC 打开失败不应让整个节点崩溃 (跳过该设备)
                logger.warning("  device[%d] 打开失败, 跳过: %s (可能被占用或 USB 异常)", i, e)
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

                self._devices[cid] = device
                # 创建 Pipeline（整个节点生命周期内复用，不反复创建销毁）
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

    def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict:
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
        need_color = stream_type in ("raw", "annotated", "mask")
        need_depth = stream_type == "depth"
        need_ir = stream_type in ("ir", "ir_annotated")

        if need_color:
            try:
                config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR).get_default_video_stream_profile())
            except OBError:
                pass
        if need_depth:
            try:
                config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR).get_default_video_stream_profile())
            except OBError:
                pass
        if need_ir:
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
        self._stream_types[camera_id] = stream_type
        t = threading.Thread(target=self._capture_loop, args=(camera_id,), daemon=True)
        self._threads[camera_id] = t
        t.start()
        logger.info("Stream started: %s type=%s need_color=%s need_depth=%s need_ir=%s",
                    camera_id, stream_type, need_color, need_depth, need_ir)
        return {"success": True, "message": f"Streaming {camera_id}"}

    def stop_stream(self, camera_id: str) -> dict:
        if camera_id not in self._cameras:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}
        self._streaming[camera_id] = False
        t = self._threads.pop(camera_id, None)
        if t and t.is_alive():
            t.join(timeout=2.0)
        # 只停止视频流，不销毁 Pipeline
        p = self._pipelines.get(camera_id)
        if p:
            try: p.stop()
            except Exception: pass
        with self._lock:
            self._color_frames[camera_id] = None
            self._depth_frames[camera_id] = None
            self._ir_frames[camera_id] = None
        logger.info("Stream stopped: %s (pipeline preserved)", camera_id)
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
        pipeline = self._pipelines.get(camera_id)
        if pipeline is None:
            return
        fps = max(self._cameras[camera_id].color_fps, 15)
        interval = 1.0 / fps
        error_count = 0
        max_errors = 10
        empty_count = 0
        max_empty = 5  # wait_for_frames 超时 1000ms, 5 次=约 5s 无帧才重启
        stream_type = self._stream_types.get(camera_id, "raw")

        while self._running and self._streaming.get(camera_id, False):
            try:
                # 超时 1000ms (对齐奥比中光官方示例, 100ms 过短易误判重启)
                frames = pipeline.wait_for_frames(1000)
                if frames is None:
                    empty_count += 1
                    if empty_count >= max_empty:
                        logger.warning("No frames for %s for ~5s, restarting streams", camera_id)
                        self._restart_streams(camera_id, stream_type)
                        pipeline = self._pipelines.get(camera_id)
                        empty_count = 0
                        error_count = 0
                    continue
                empty_count = 0

                # 只采集当前流类型需要的帧
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
                error_count = 0
            except Exception:
                error_count += 1
                logger.exception("Capture error: %s (consecutive: %d)", camera_id, error_count)
                if error_count >= max_errors:
                    logger.warning("Too many capture errors for %s, restarting streams", camera_id)
                    self._restart_streams(camera_id, stream_type)
                    pipeline = self._pipelines.get(camera_id)
                    error_count = 0
                    empty_count = 0
            time.sleep(interval)

    def _restart_streams(self, camera_id: str, stream_type: str = "raw"):
        """停止并重新启动 Pipeline 的视频流（不销毁 Pipeline 对象，只开启需要的流）。"""
        pipeline = self._pipelines.get(camera_id)
        if pipeline is None:
            return
        try: pipeline.stop()
        except Exception: pass
        time.sleep(0.5)

        from pyorbbecsdk import Config, OBSensorType
        config = Config()
        need_color = stream_type in ("raw", "annotated", "mask")
        need_depth = stream_type == "depth"
        need_ir = stream_type in ("ir", "ir_annotated")

        if need_color:
            config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR).get_default_video_stream_profile())
        if need_depth:
            config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR).get_default_video_stream_profile())
        if need_ir:
            try:
                config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.IR_SENSOR).get_default_video_stream_profile())
            except Exception:
                try:
                    config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.LEFT_IR_SENSOR).get_default_video_stream_profile())
                except Exception:
                    pass
        pipeline.start(config)
        logger.info("Streams restarted for %s type=%s", camera_id, stream_type)

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
        """IR 帧 → uint8 灰度图 (多级去噪: 中值滤波→高斯模糊→形态学开运算)。"""
        from pyorbbecsdk import OBFormat
        w, h, fmt = frame.get_width(), frame.get_height(), frame.get_format()
        raw = np.frombuffer(frame.get_data(), dtype=np.uint8)

        if fmt == OBFormat.Y8:
            gray = raw.reshape((h, w)).copy()
        elif fmt in (OBFormat.Y16, OBFormat.YUYV, OBFormat.YUY2):
            raw_u16 = raw.view(np.uint16).reshape((h, w))
            try:
                bit_size = frame.pixel_available_bit_size()
            except Exception:
                bit_size = 16
            scale = 1.0 / (2 ** (bit_size - 8)) if bit_size > 8 else 1.0
            gray = (raw_u16.astype(np.float32) * scale).clip(0, 255).astype(np.uint8)
        elif fmt == OBFormat.MJPG:
            gray = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
        else:
            return None

        if gray is None:
            return None

        # ---- 多级去噪 ----
        gray = cv2.medianBlur(gray, 5)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)

        return gray

    def shutdown(self):
        self._running = False
        for cid in list(self._streaming):
            if self._streaming[cid]:
                self.stop_stream(cid)
        # 清理所有残留 pipeline 和 device
        for cid in list(self._pipelines.keys()):
            try: self._pipelines[cid].stop()
            except Exception: pass
        self._pipelines.clear()
        self._devices.clear()
        self._cameras.clear()
        logger.info("CameraManager shutdown complete")


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
                                frame = _annotate_frame(self._manager, camera_id, frame)
                            except Exception:
                                logger.exception("annotated frame generation failed")
                    elif stream_type == "mask":
                        frame = self._manager.get_latest_color(camera_id)
                        if frame is not None:
                            try:
                                frame = _yolo_annotate_frame(self._manager, camera_id, frame)
                            except Exception:
                                logger.exception("mask frame generation failed")
                    elif stream_type == "ir_annotated":
                        frame = self._manager.get_latest_ir(camera_id)
                        if frame is not None:
                            try:
                                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                                frame = _annotate_frame(self._manager, camera_id, frame)
                            except Exception:
                                logger.exception("ir_annotated frame generation failed")
                    elif stream_type == "mask_ir":
                        frame = self._manager.get_latest_ir(camera_id)
                        if frame is not None:
                            try:
                                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                                frame = _yolo_annotate_frame(self._manager, camera_id, frame)
                            except Exception:
                                logger.exception("mask_ir frame generation failed")
                    else:
                        # raw 及其它: 取彩色帧
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
                    logger.exception("push_loop error: %s/%s", camera_id, stream_type)
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
                        await ws.send(json.dumps({"type": "error", "message": f"Camera {camera_id} not streaming. Start stream first via API."}))
                        continue
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
    server = None
    try:
        import websockets as ws_lib
        proto = _WsProtocol(manager)

        async def handler(websocket):
            await proto.handle(websocket)

        server = await ws_lib.serve(handler, WS_HOST, WS_PORT, reuse_port=True)
        logger.info("WS server listening on %s:%d", WS_HOST, WS_PORT)

        # 等待直到manager停止
        while manager._running:
            await asyncio.sleep(0.5)

        # 优雅关闭
        server.close()
        await server.wait_closed()
        logger.info("WS server closed")
    except OSError as e:
        if e.errno == 98:
            logger.warning("WS port %d still in use, retrying after 2s...", WS_PORT)
            await asyncio.sleep(2.0)
            try:
                server = await ws_lib.serve(handler, WS_HOST, WS_PORT, reuse_port=True)
                logger.info("WS server listening on %s:%d (retry)", WS_HOST, WS_PORT)
                while manager._running:
                    await asyncio.sleep(0.5)
                server.close()
                await server.wait_closed()
                logger.info("WS server closed")
            except OSError as e2:
                logger.error("WS port %d still unavailable: %s", WS_PORT, e2)
        else:
            logger.exception("WS server error")
    except ImportError:
        logger.warning("websockets package not installed. Install: pip install websockets")
        logger.warning("WS server NOT started. Video streaming unavailable.")
    except Exception:
        logger.exception("WS server crashed")
    finally:
        if server:
            server.close()


def _run_ws_in_thread(manager: CameraManager):
    """在独立线程中运行 asyncio event loop 驱动 WS server。"""
    import socket
    # 检查端口是否被占用，如果是则尝试清理
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', WS_PORT))
    sock.close()
    if result == 0:
        logger.warning("WS port %d is already in use, attempting to reuse", WS_PORT)

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

    # QRDetector + stability tracker + pose averager for annotated stream (per camera)
    _qr_detectors: dict[str, object] = {}
    _stability_trackers: dict[str, PoseStabilityTracker] = {}
    _pose_averagers: dict[str, list] = {}  # camera_id -> list of (tvec, rvec) for sliding average
    POSE_AVG_WINDOW = 10  # 滑动平均窗口大小

    for cid, cfg in _cam_configs.items():
        calib = cfg.get("calibration", {})
        intrinsics = calib.get("color_intrinsics", {})
        _pose_averagers[cid] = []
        if intrinsics.get("fx"):
            try:
                from python_pkgs.orbbec_vision.qr_detector import QRDetector
                K = np.array([
                    [intrinsics["fx"], 0, intrinsics["cx"]],
                    [0, intrinsics["fy"], intrinsics["cy"]],
                    [0, 0, 1],
                ], dtype=np.float64)
                D = np.array(intrinsics.get("distortion", [0, 0, 0, 0, 0]), dtype=np.float64)
                _qr_detectors[cid] = QRDetector(K, D)
                _stability_trackers[cid] = PoseStabilityTracker(60)
                logger.info("QRDetector + stability tracker ready for camera '%s'", cid)
            except Exception:
                logger.exception("Failed to create QRDetector for camera '%s'", cid)

    manager._qr_detectors = _qr_detectors
    manager._stability_trackers = _stability_trackers
    manager._stability_trackers_per_id = {}  # camera_id -> {qr_id: PoseStabilityTracker}

    # ---- YOLO 分割检测模块 (per camera, 供 mask 流与后续点云模块使用) ----
    _yolo_detectors: dict[str, object] = {}
    _yolo_dir = _config_dir  # orbbec_vision 目录 (yolo_config.yaml 所在)
    try:
        _yolo_cfg_path = os.path.join(_yolo_dir, "yolo_config.yaml")
        with open(_yolo_cfg_path) as _f:
            _yolo_cfg = _yaml.safe_load(_f) or {}
        if _yolo_cfg.get("enabled", True):
            from python_pkgs.orbbec_vision.yolo_detector import YOLODetector
            _base_names = _yolo_cfg.get("names") or ["object"]
            _per_cam = _yolo_cfg.get("per_camera", {}) or {}
            # 只为实际连接的相机构建 detector (避免为未连接相机浪费资源)
            for cid, cam_info in manager._cameras.items():
                if not cam_info.connected:
                    continue
                cam_cfg = {**_yolo_cfg, **(_per_cam.get(cid, {}) or {})}
                # 环境变量覆盖模型路径 (YOLO_MODEL_PATH, 优先 per-camera: YOLO_MODEL_PATH_<cid>)
                env_path = os.environ.get(f"YOLO_MODEL_PATH_{cid}") or os.environ.get("YOLO_MODEL_PATH")
                model_path = env_path or cam_cfg.get("model_path", "")
                if model_path and not os.path.isabs(model_path):
                    model_path = os.path.join(_yolo_dir, model_path)
                if not model_path or not os.path.isfile(model_path):
                    logger.warning("YOLO model not found for camera '%s' (path=%s), "
                                   "mask stream will degrade to raw", cid, model_path)
                    _yolo_detectors[cid] = None
                    continue
                try:
                    _yolo_detectors[cid] = YOLODetector(
                        model_path=model_path,
                        names=cam_cfg.get("names", _base_names),
                        conf=float(cam_cfg.get("conf", 0.5)),
                        iou=float(cam_cfg.get("iou", 0.45)),
                        imgsz=int(cam_cfg.get("imgsz", 640)),
                        device=cam_cfg.get("device", "cpu"),
                    )
                    logger.info("YOLODetector ready for camera '%s'", cid)
                except Exception:
                    logger.exception("Failed to create YOLODetector for camera '%s'", cid)
                    _yolo_detectors[cid] = None
        else:
            logger.info("YOLO module disabled by config")
    except Exception:
        logger.exception("Failed to init YOLO module (mask stream degrades to raw)")
    manager._yolo_detectors = _yolo_detectors

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
        stream_type = params.get("stream_type", "raw")
        result = manager.start_stream(camera_id, stream_type)
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

    # /camera/calibrate (GenericCommand)
    def _handle_calibrate(request, response):
        if _qr_calibrator is None:
            response.success = False
            response.message = "QRCalibrator not available"
            return response
        params = json.loads(request.params_json) if request.params_json else {}
        camera_id = params.get("camera_id", "")
        arm = params.get("arm", "right")
        stream_type = params.get("stream_type", "color") or "color"

        # 自动按需启动推流
        was_streaming = manager.is_streaming(camera_id)
        if not was_streaming:
            stream_to_start = "ir" if stream_type == "ir" else "raw"
            result = manager.start_stream(camera_id, stream_to_start)
            if not result["success"]:
                response.success = False
                response.message = f"Failed to start stream: {result['message']}"
                return response
            for _ in range(30):
                frame = (manager.get_latest_ir(camera_id) if stream_type == "ir"
                         else manager.get_latest_color(camera_id))
                if frame is not None:
                    break
                time.sleep(0.1)

        try:
            # 采集多帧做平均检测 — 用时间戳确保每帧都是新帧
            calib_frames = []
            # 丢弃启动残留, 等第一帧新数据
            last_ts = manager.get_frame_timestamp(camera_id)
            wait_t0 = time.time()
            while manager.get_frame_timestamp(camera_id) == last_ts:
                if time.time() - wait_t0 > 2.0: break
                time.sleep(0.01)
            last_ts = manager.get_frame_timestamp(camera_id)

            for _ in range(20):
                wait_t0 = time.time()
                while True:
                    cur_ts = manager.get_frame_timestamp(camera_id)
                    if cur_ts > last_ts:
                        last_ts = cur_ts
                        break
                    if time.time() - wait_t0 > 1.0: break
                    time.sleep(0.005)
                cf = manager.get_latest_color(camera_id)
                irf = manager.get_latest_ir(camera_id)
                frame = cf if stream_type == "color" else irf
                if frame is not None:
                    calib_frames.append(frame)
            # 兼容: 优先用 qr_ids 列表; 否则用单个 qr_id
            qr_ids_param = params.get("qr_ids")
            if qr_ids_param is None:
                qid = params.get("qr_id")
                qr_ids_param = [int(qid)] if qid is not None else []
            else:
                qr_ids_param = [int(x) for x in qr_ids_param]

            result = _qr_calibrator.calibrate(
                camera_id=params.get("camera_id", ""),
                arm=arm,
                qr_ids=qr_ids_param,
                marker_size=params.get("marker_size", 0.058),
                point_name=params.get("point_name", ""),
                scene_id=params.get("scene_id", ""),
                stream_type=stream_type,
                frames=calib_frames if calib_frames else None,
            )
            response.success = result["success"]
            response.message = result["message"]
            if result["success"]:
                response.result_json = json.dumps({
                    "translation": result.get("translation", []),
                    "rotation": result.get("rotation", []),
                    "qr_ids_calibrated": result.get("qr_ids_calibrated", []),
                    "T_qr_ee_per_id": result.get("T_qr_ee_per_id", {}),
                })
        finally:
            if not was_streaming:
                manager.stop_stream(camera_id)
        return response

    node.create_service(GenericCommand, "/camera/calibrate", _handle_calibrate)

    # /camera/scene (GenericCommand)
    def _handle_scene(request, response):
        if _scene_manager is None:
            response.success = False
            response.message = "SceneManager not available"
            return response
        params = json.loads(request.params_json) if request.params_json else {}
        action = params.get("action", "list")
        scene_id = params.get("scene_id", "")
        # 点位数据在 params_json 字段中（由 camera_client 打包）
        extra = json.loads(params.get("params_json", "{}")) if isinstance(params.get("params_json"), str) else (params.get("params_json") or {})
        try:
            if action == "list":
                result = _scene_manager.list_scenes()
                response.success = True
                response.result_json = json.dumps(result)
            elif action == "get":
                data = _scene_manager.get_scene(scene_id)
                if data is None:
                    response.success = False
                    response.message = f"Scene not found: {scene_id}"
                else:
                    response.success = True
                    response.result_json = json.dumps(data)
            elif action == "create":
                ok = _scene_manager.create_scene(scene_id, extra.get("description", ""))
                response.success = ok
                response.message = "Created" if ok else f"Already exists: {scene_id}"
            elif action == "delete":
                ok = _scene_manager.delete_scene(scene_id)
                response.success = ok
                response.message = "Deleted" if ok else f"Not found: {scene_id}"
            elif action == "add_point":
                ok = _scene_manager.add_point(
                    scene_id=scene_id,
                    name=extra.get("name", ""),
                    arm=extra.get("arm", "right"),
                    marker_size=extra.get("marker_size", 0.058),
                    stream_type=extra.get("stream_type", "color"),
                    qr_ids=extra.get("qr_ids"),
                    T_qr_ee_per_id=extra.get("T_qr_ee_per_id"),
                    qr_id=extra.get("qr_id"),
                    T_qr_workspace=extra.get("T_qr_workspace"),
                )
                response.success = ok
                response.message = "Point added" if ok else "Failed"
            elif action == "delete_point":
                ok = _scene_manager.delete_point(scene_id, extra.get("name", ""))
                response.success = ok
                response.message = "Point deleted" if ok else "Not found"
            elif action == "update_point":
                update_kwargs = {k: v for k, v in extra.items() if k != "name"}
                ok = _scene_manager.update_point(scene_id, extra.get("name", ""), **update_kwargs)
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

    node.create_service(GenericCommand, "/camera/scene", _handle_scene)

    # /camera/compute_pose (GenericCommand)
    def _handle_compute_pose(request, response):
        if _scene_manager is None:
            response.success = False
            response.message = "SceneManager not available"
            return response
        params = json.loads(request.params_json) if request.params_json else {}
        try:
            camera_id = params.get("camera_id", "")
            scene_id = params.get("scene_id", "")
            point_name = params.get("point_name", "")

            point = _scene_manager.find_point(scene_id, point_name)
            if point is None:
                response.success = False
                response.message = f"Point not found: {scene_id}/{point_name}"
                return response
            logger.info("compute_pose: loaded point '%s' from scene '%s': arm=%s qr_ids=%s marker_size=%s stream_type=%s",
                        point_name, scene_id, point.get("arm"), point.get("qr_ids"),
                        point.get("marker_size"), point.get("stream_type", "color"))

            qr_ids_allowed = point.get("qr_ids", []) or []
            T_qr_ee_per_id = point.get("T_qr_ee_per_id", {}) or {}
            if not T_qr_ee_per_id:
                response.success = False
                response.message = "Point has no calibrated T_qr_ee_per_id"
                return response

            # 兼容性: 如果 qr_ids 与 T_qr_ee_per_id 的 keys 不一致 (旧数据 normalize 的产物),
            # 以 T_qr_ee_per_id 的 keys 为准 — 因为只有标定过的 QR 才能用
            calibrated_ids = {int(k) for k in T_qr_ee_per_id.keys()}
            if qr_ids_allowed and set(qr_ids_allowed) != calibrated_ids:
                logger.warning("compute_pose: qr_ids %s mismatch with calibrated keys %s, using calibrated",
                               qr_ids_allowed, sorted(calibrated_ids))
                qr_ids_allowed = list(calibrated_ids)
            elif not qr_ids_allowed:
                qr_ids_allowed = list(calibrated_ids)

            cfg = _cam_configs.get(camera_id, {})
            calib = cfg.get("calibration", {})
            intrinsics = calib.get("color_intrinsics", {})
            if not intrinsics.get("fx"):
                response.success = False
                response.message = f"No intrinsics for camera: {camera_id}"
                return response

            point_stream_type = point.get("stream_type", "color")
            marker_size = point.get("marker_size", 0.058)

            # 自动按需启动推流
            was_streaming = manager.is_streaming(camera_id)
            if not was_streaming:
                stream_to_start = "ir" if point_stream_type == "ir" else "raw"
                result = manager.start_stream(camera_id, stream_to_start)
                if not result["success"]:
                    response.success = False
                    response.message = f"Failed to start stream: {result['message']}"
                    return response
                for _ in range(30):
                    frame = (manager.get_latest_ir(camera_id) if point_stream_type == "ir"
                             else manager.get_latest_color(camera_id))
                    if frame is not None:
                        break
                    time.sleep(0.1)

            try:
                from python_pkgs.orbbec_vision.qr_detector import QRDetector
                import numpy as np
                K = np.array([[intrinsics["fx"], 0, intrinsics["cx"]], [0, intrinsics["fy"], intrinsics["cy"]], [0, 0, 1]], dtype=np.float64)
                D = np.array(intrinsics.get("distortion", [0,0,0,0,0]), dtype=np.float64)
                detector = QRDetector(K, D)

                target_frames = 10
                # 每个 QR id 的多帧观测: id -> list of (tvec, rvec, corner_area)
                per_id_obs: dict[int, list[tuple]] = {}
                max_attempts = target_frames * 5

                # 等待第一帧新数据
                last_ts = manager.get_frame_timestamp(camera_id)
                wait_t0 = time.time()
                while manager.get_frame_timestamp(camera_id) == last_ts:
                    if time.time() - wait_t0 > 2.0: break
                    time.sleep(0.01)
                last_ts = manager.get_frame_timestamp(camera_id)

                frames_used = 0
                for _attempt in range(max_attempts):
                    wait_t0 = time.time()
                    while True:
                        cur_ts = manager.get_frame_timestamp(camera_id)
                        if cur_ts > last_ts:
                            last_ts = cur_ts
                            break
                        if time.time() - wait_t0 > 1.0: break
                        time.sleep(0.005)

                    color_frame = manager.get_latest_color(camera_id)
                    ir_frame = manager.get_latest_ir(camera_id)
                    if point_stream_type == "ir":
                        frame = ir_frame if ir_frame is not None else color_frame
                    else:
                        frame = color_frame if color_frame is not None else ir_frame
                    if frame is None:
                        continue
                    results = detector.detect(frame, marker_size)
                    for r in results:
                        # 允许列表为空 = 通配; 且 QR 必须有标定数据
                        if qr_ids_allowed and r.qr_id not in qr_ids_allowed:
                            continue
                        if str(r.qr_id) not in T_qr_ee_per_id:
                            continue
                        area = _corner_area(r.corners)
                        per_id_obs.setdefault(r.qr_id, []).append(
                            (np.asarray(r.tvec).ravel(), np.asarray(r.rvec).ravel(), area)
                        )
                    frames_used += 1
                    if frames_used >= target_frames:
                        break

                if not per_id_obs:
                    response.success = False
                    response.message = f"No allowed QR detected (allowed={qr_ids_allowed or 'any'})"
                    return response
            finally:
                if not was_streaming:
                    manager.stop_stream(camera_id)

            logger.info("compute_pose: collected observations from %d QRs over %d frames",
                        len(per_id_obs), frames_used)

            import cv2 as _cv2

            # T_camera_ee from config (公共)
            arm = point.get("arm", "right")
            arm_letter = arm[0].upper() if arm else "R"
            ee_link = f"ARM-{arm_letter}-J7_Link"
            cam_to_ee = calib.get(f"camera_to_{ee_link}", {})
            if not cam_to_ee.get("translation"):
                response.success = False
                response.message = f"No camera_to_ee calibration for {ee_link}"
                return response
            R_cam_ee, _ = _cv2.Rodrigues(np.array(cam_to_ee["rotation"], dtype=np.float64))
            T_cam_ee = np.eye(4); T_cam_ee[:3,:3] = R_cam_ee
            t_raw = cam_to_ee["translation"]
            T_cam_ee[:3,3] = [float(t_raw[0])/1000.0 if abs(t_raw[0])>10 else float(t_raw[0]),
                              float(t_raw[1])/1000.0 if abs(t_raw[1])>10 else float(t_raw[1]),
                              float(t_raw[2])/1000.0 if abs(t_raw[2])>10 else float(t_raw[2])]

            # 从 TF 获取当前末端位姿
            T_base_ee_now = _get_T_base_ee(arm)
            if T_base_ee_now is None:
                response.success = False
                response.message = f"TF not available for arm={arm}"
                return response

            # 对每个 QR 各自算 T_base_ee_target_i
            # OpenCV 光学系(X右/Y下/Z前) → ROS link 约定(X前/Y左/Z上) 旋转
            R_link_optical = np.array([
                [ 0,  0,  1],
                [-1,  0,  0],
                [ 0, -1,  0],
            ], dtype=np.float64)
            T_link_optical = np.eye(4); T_link_optical[:3, :3] = R_link_optical

            candidates: list[dict] = []  # [{qr_id, t (3,), q (4,) xyzw, weight}]
            for qid, obs in per_id_obs.items():
                if len(obs) < 3:
                    logger.info("  skip QR id=%d (only %d obs)", qid, len(obs))
                    continue
                # 多帧平均当前 QR 在相机系中的位姿
                tvecs = np.array([o[0] for o in obs])
                rvecs = np.array([o[1] for o in obs])
                areas = np.array([o[2] for o in obs])
                avg_tvec_qr = np.mean(tvecs, axis=0)
                avg_rvec_qr = np.mean(rvecs, axis=0)
                avg_area = float(np.mean(areas))

                R_cam_qr, _ = _cv2.Rodrigues(avg_rvec_qr)
                T_cam_qr_optical = np.eye(4); T_cam_qr_optical[:3,:3] = R_cam_qr; T_cam_qr_optical[:3,3] = avg_tvec_qr

                # 光学系 → link 约定: T_camlink_qr = R_link_optical @ T_optical_qr
                T_cam_qr_i = T_link_optical @ T_cam_qr_optical

                T_qr_ee_data = T_qr_ee_per_id[str(qid)]
                t_qe = T_qr_ee_data.get("translation", [0,0,0])
                r_qe = T_qr_ee_data.get("rotation", [0,0,0,1])
                qx, qy, qz, qw = r_qe
                R_qr_ee = np.array([
                    [1-2*qy*qy-2*qz*qz, 2*qx*qy-2*qz*qw, 2*qx*qz+2*qy*qw],
                    [2*qx*qy+2*qz*qw, 1-2*qx*qx-2*qz*qz, 2*qy*qz-2*qx*qw],
                    [2*qx*qz-2*qy*qw, 2*qy*qz+2*qx*qw, 1-2*qx*qx-2*qy*qy]])
                T_qr_ee_mat = np.eye(4); T_qr_ee_mat[:3,:3] = R_qr_ee; T_qr_ee_mat[:3,3] = t_qe

                T_ee_qr_i = np.linalg.inv(T_cam_ee) @ T_cam_qr_i
                T_base_qr_i = T_base_ee_now @ T_ee_qr_i
                T_target_i = T_base_qr_i @ T_qr_ee_mat

                # 提取 translation + quaternion (xyzw)
                t_i = T_target_i[:3, 3].copy()
                Ri = T_target_i[:3, :3]
                tr = np.trace(Ri)
                if tr > 0:
                    S = np.sqrt(tr + 1.0) * 2
                    qw_i = 0.25 * S
                    qx_i = (Ri[2,1] - Ri[1,2]) / S
                    qy_i = (Ri[0,2] - Ri[2,0]) / S
                    qz_i = (Ri[1,0] - Ri[0,1]) / S
                elif Ri[0,0] > Ri[1,1] and Ri[0,0] > Ri[2,2]:
                    S = np.sqrt(1.0 + Ri[0,0] - Ri[1,1] - Ri[2,2]) * 2
                    qw_i = (Ri[2,1] - Ri[1,2]) / S
                    qx_i = 0.25 * S
                    qy_i = (Ri[0,1] + Ri[1,0]) / S
                    qz_i = (Ri[0,2] + Ri[2,0]) / S
                elif Ri[1,1] > Ri[2,2]:
                    S = np.sqrt(1.0 + Ri[1,1] - Ri[0,0] - Ri[2,2]) * 2
                    qw_i = (Ri[0,2] - Ri[2,0]) / S
                    qx_i = (Ri[0,1] + Ri[1,0]) / S
                    qy_i = 0.25 * S
                    qz_i = (Ri[1,2] + Ri[2,1]) / S
                else:
                    S = np.sqrt(1.0 + Ri[2,2] - Ri[0,0] - Ri[1,1]) * 2
                    qw_i = (Ri[1,0] - Ri[0,1]) / S
                    qx_i = (Ri[0,2] + Ri[2,0]) / S
                    qy_i = (Ri[1,2] + Ri[2,1]) / S
                    qz_i = 0.25 * S
                q_i = np.array([qx_i, qy_i, qz_i, qw_i])
                q_i = q_i / np.linalg.norm(q_i)

                candidates.append({
                    "qr_id": qid, "t": t_i, "q": q_i,
                    "weight": avg_area, "n_obs": len(obs),
                })
                logger.info("  QR id=%d (%d obs, area=%.0f): t=[%.4f,%.4f,%.4f]",
                            qid, len(obs), avg_area, t_i[0], t_i[1], t_i[2])

            if not candidates:
                response.success = False
                response.message = "No QR had enough observations"
                return response

            # MAD 离群剔除 (基于平移)
            ts = np.array([c["t"] for c in candidates])
            if len(candidates) >= 3:
                keep_mask = _mad_filter(ts, threshold=3.0)
                filtered = [c for c, k in zip(candidates, keep_mask) if k]
                if filtered:
                    rejected_ids = [c["qr_id"] for c, k in zip(candidates, keep_mask) if not k]
                    if rejected_ids:
                        logger.info("  MAD rejected QRs: %s", rejected_ids)
                    candidates = filtered
                else:
                    logger.warning("  MAD rejected all candidates, fallback to original set")

            # 加权融合
            ts_arr = np.array([c["t"] for c in candidates])
            qs_arr = np.array([c["q"] for c in candidates])
            ws_arr = np.array([c["weight"] for c in candidates])
            ws_arr = ws_arr / np.sum(ws_arr)

            fused_t = np.sum(ts_arr * ws_arr[:, None], axis=0)
            fused_q = _quat_weighted_mean(qs_arr, ws_arr)

            # quat → matrix → rpy
            qx_f, qy_f, qz_f, qw_f = fused_q
            R_fused = np.array([
                [1-2*qy_f*qy_f-2*qz_f*qz_f, 2*qx_f*qy_f-2*qz_f*qw_f, 2*qx_f*qz_f+2*qy_f*qw_f],
                [2*qx_f*qy_f+2*qz_f*qw_f, 1-2*qx_f*qx_f-2*qz_f*qz_f, 2*qy_f*qz_f-2*qx_f*qw_f],
                [2*qx_f*qz_f-2*qy_f*qw_f, 2*qy_f*qz_f+2*qx_f*qw_f, 1-2*qx_f*qx_f-2*qy_f*qy_f]])
            sy = np.sqrt(R_fused[0,0]**2 + R_fused[1,0]**2)
            singular = sy < 1e-6
            roll = float(np.arctan2(-R_fused[1,2], R_fused[1,1]) if singular else np.arctan2(R_fused[2,1], R_fused[2,2]))
            pitch = float(np.arctan2(-R_fused[2,0], sy))
            yaw = float(0.0 if singular else np.arctan2(R_fused[1,0], R_fused[0,0]))

            x, y, z = float(fused_t[0]), float(fused_t[1]), float(fused_t[2])

            # 转换为 mm + 度
            x_mm = x * 1000.0
            y_mm = y * 1000.0
            z_mm = z * 1000.0
            roll_deg = float(np.degrees(roll))
            pitch_deg = float(np.degrees(pitch))
            yaw_deg = float(np.degrees(yaw))

            response.success = True
            response.message = "Computed"
            response.result_json = json.dumps({
                "x": x_mm, "y": y_mm, "z": z_mm,
                "roll": roll_deg, "pitch": pitch_deg, "yaw": yaw_deg,
            })
            logger.info("compute_pose: fused %d QRs (weights=%s)",
                        len(candidates), [f"{w:.2f}" for w in ws_arr])
            logger.info("compute_pose: result T_base_ee_target → xyz(m)=[%.4f,%.4f,%.4f] rpy(rad)=[%.4f,%.4f,%.4f]",
                        x, y, z, roll, pitch, yaw)
            logger.info("compute_pose: output (mm+deg) → xyz=[%.2f,%.2f,%.2f] rpy=[%.2f,%.2f,%.2f]",
                        x_mm, y_mm, z_mm, roll_deg, pitch_deg, yaw_deg)
        except Exception as e:
            logger.exception("compute_pose failed")
            response.success = False
            response.message = str(e)
        return response

    node.create_service(GenericCommand, "/camera/compute_pose", _handle_compute_pose)

    # ---- TF Broadcaster + Listener ----
    import tf2_ros
    _tf_broadcaster = tf2_ros.TransformBroadcaster(node)
    _tf_buffer = tf2_ros.Buffer()
    _tf_listener = tf2_ros.TransformListener(_tf_buffer, node)
    _tf_timer = None

    # 帮助函数: 从 TF 获取 base_link → ee_link 的 4x4 变换
    def _get_T_base_ee(arm: str):
        import numpy as np
        from rclpy.duration import Duration
        arm_letter = arm[0].upper() if arm else "R"
        ee_link = f"ARM-{arm_letter}-J7_Link"
        try:
            tf_msg = _tf_buffer.lookup_transform("base_link", ee_link,
                                                 rclpy.time.Time(),
                                                 timeout=Duration(seconds=1.0))
            t = tf_msg.transform.translation
            q = tf_msg.transform.rotation
            qx, qy, qz, qw = q.x, q.y, q.z, q.w
            R = np.array([
                [1-2*qy*qy-2*qz*qz, 2*qx*qy-2*qz*qw, 2*qx*qz+2*qy*qw],
                [2*qx*qy+2*qz*qw, 1-2*qx*qx-2*qz*qz, 2*qy*qz-2*qx*qw],
                [2*qx*qz-2*qy*qw, 2*qy*qz+2*qx*qw, 1-2*qx*qx-2*qy*qy],
            ])
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = [t.x, t.y, t.z]
            # 旋转矩阵 → xyz 欧拉角 (deg)
            sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
            singular = sy < 1e-6
            if not singular:
                roll = float(np.degrees(np.arctan2(R[2, 1], R[2, 2])))
                pitch = float(np.degrees(np.arctan2(-R[2, 0], sy)))
                yaw = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))
            else:
                roll = float(np.degrees(np.arctan2(-R[1, 2], R[1, 1])))
                pitch = float(np.degrees(np.arctan2(-R[2, 0], sy)))
                yaw = 0.0
            logger.info("TF lookup base_link→%s: trans=[%.4f, %.4f, %.4f] rpy(deg)=[%.2f, %.2f, %.2f] quat(xyzw)=[%.4f, %.4f, %.4f, %.4f]",
                        ee_link, t.x, t.y, t.z, roll, pitch, yaw, qx, qy, qz, qw)
            return T
        except Exception as e:
            logger.warning("TF lookup base_link→%s failed: %s", ee_link, e)
            return None

    def _publish_calibration_tfs():
        """读取 config 中的 camera_to_<ee_link> 并发布 TF。

        config 存储的是 camera→ee 变换 (rodrigues + translation),
        发布时需要发 ee→camera (倒置), 让相机挂在末端 link 下,
        这样 TF 树是 base_link → ... → ee_link → camera_link.
        """
        for cid, cfg in _cam_configs.items():
            try:
                calib = cfg.get("calibration", {})
                for key, transform in calib.items():
                    if not key.startswith("camera_to_"):
                        continue
                    ee_link = key[len("camera_to_"):]
                    t = transform.get("translation", [0, 0, 0])
                    r = transform.get("rotation", [0, 0, 0])
                    import cv2 as _cv2
                    # config: camera→ee, 构建 4x4
                    R_cam_ee, _ = _cv2.Rodrigues(np.array(r, dtype=np.float64))
                    t_cam_ee = np.array([
                        float(t[0]) / 1000.0 if abs(t[0]) > 10 else float(t[0]),
                        float(t[1]) / 1000.0 if abs(t[1]) > 10 else float(t[1]),
                        float(t[2]) / 1000.0 if abs(t[2]) > 10 else float(t[2]),
                    ])
                    T_cam_ee = np.eye(4)
                    T_cam_ee[:3, :3] = R_cam_ee
                    T_cam_ee[:3, 3] = t_cam_ee
                    # 倒置: ee→camera
                    T_ee_cam = np.linalg.inv(T_cam_ee)
                    R_ee_cam = T_ee_cam[:3, :3]
                    t_ee_cam = T_ee_cam[:3, 3]

                    from geometry_msgs.msg import TransformStamped
                    _tf_msg = TransformStamped()
                    _tf_msg.header.stamp = node.get_clock().now().to_msg()
                    _tf_msg.header.frame_id = ee_link  # 父: 末端 link
                    _tf_msg.child_frame_id = f"{cid}_camera_link"  # 子: 相机 frame
                    _tf_msg.transform.translation.x = float(t_ee_cam[0])
                    _tf_msg.transform.translation.y = float(t_ee_cam[1])
                    _tf_msg.transform.translation.z = float(t_ee_cam[2])
                    # rotation matrix → quaternion
                    tr = np.trace(R_ee_cam)
                    if tr > 0:
                        S = np.sqrt(tr + 1.0) * 2
                        qw = 0.25 * S
                        qx = (R_ee_cam[2, 1] - R_ee_cam[1, 2]) / S
                        qy = (R_ee_cam[0, 2] - R_ee_cam[2, 0]) / S
                        qz = (R_ee_cam[1, 0] - R_ee_cam[0, 1]) / S
                    elif R_ee_cam[0, 0] > R_ee_cam[1, 1] and R_ee_cam[0, 0] > R_ee_cam[2, 2]:
                        S = np.sqrt(1.0 + R_ee_cam[0, 0] - R_ee_cam[1, 1] - R_ee_cam[2, 2]) * 2
                        qw = (R_ee_cam[2, 1] - R_ee_cam[1, 2]) / S
                        qx = 0.25 * S
                        qy = (R_ee_cam[0, 1] + R_ee_cam[1, 0]) / S
                        qz = (R_ee_cam[0, 2] + R_ee_cam[2, 0]) / S
                    elif R_ee_cam[1, 1] > R_ee_cam[2, 2]:
                        S = np.sqrt(1.0 + R_ee_cam[1, 1] - R_ee_cam[0, 0] - R_ee_cam[2, 2]) * 2
                        qw = (R_ee_cam[0, 2] - R_ee_cam[2, 0]) / S
                        qx = (R_ee_cam[0, 1] + R_ee_cam[1, 0]) / S
                        qy = 0.25 * S
                        qz = (R_ee_cam[1, 2] + R_ee_cam[2, 1]) / S
                    else:
                        S = np.sqrt(1.0 + R_ee_cam[2, 2] - R_ee_cam[0, 0] - R_ee_cam[1, 1]) * 2
                        qw = (R_ee_cam[1, 0] - R_ee_cam[0, 1]) / S
                        qx = (R_ee_cam[0, 2] + R_ee_cam[2, 0]) / S
                        qy = (R_ee_cam[1, 2] + R_ee_cam[2, 1]) / S
                        qz = 0.25 * S
                    _tf_msg.transform.rotation.x = float(qx)
                    _tf_msg.transform.rotation.y = float(qy)
                    _tf_msg.transform.rotation.z = float(qz)
                    _tf_msg.transform.rotation.w = float(qw)
                    _tf_broadcaster.sendTransform(_tf_msg)
                    logger.debug("TF: %s → %s published", ee_link, _tf_msg.child_frame_id)
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

#!/usr/bin/env python3
"""
QR 二维码检测测试 — 彩色 + 红外双通道
同时开启 COLOR + IR + DEPTH 三路流，硬件对齐。
调用 qr_detector.QRDetector 模块，修改直接同步到控制系统。
"""
import os
import sys

_SDK_LIB_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "lib", "python3.10",
    "site-packages", "pyorbbecsdk",
)
if os.path.isdir(_SDK_LIB_DIR):
    _ld = os.environ.get("LD_LIBRARY_PATH", "")
    if _SDK_LIB_DIR not in _ld.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{_SDK_LIB_DIR}:{_ld}" if _ld else _SDK_LIB_DIR
        os.execve(sys.executable, [sys.executable] + sys.argv, os.environ)

import cv2
import cv2.aruco as aruco
import numpy as np
from pyorbbecsdk import (
    Context, Config, OBLogLevel, OBSensorType,
    Pipeline, OBFormat, OBFrameType,
    OBPropertyID, OBPermissionType,
)

# ---- 导入 QR 检测模块 ----
import sys as _sys
_here = os.path.dirname(os.path.abspath(__file__))
_pkgs_root = os.path.normpath(os.path.join(_here, ".."))
if _pkgs_root not in _sys.path:
    _sys.path.insert(0, _pkgs_root)
from qr_detector import QRDetector, QRResult

# ---- 配置 ----
IR_WIDTH, IR_HEIGHT, IR_FPS = 640, 0, 30
COLOR_WIDTH, COLOR_HEIGHT, COLOR_FPS = 640, 0, 30
DEPTH_WIDTH, DEPTH_HEIGHT, DEPTH_FPS = 640, 0, 30
FLIP = False

# QR 检测参数
QR_DICT_ID = aruco.DICT_APRILTAG_36H11   # AprilTag tag36h11
QR_MARKER_SIZE = 0.08                  # 8cm
QR_TARGET_ID = 1                       # 目标 ID (高亮显示, 不影响检测)
QR_DICT_NAME = "APRILTAG_36H11"

# 稳定性统计窗口 (帧数)
STABILITY_WINDOW = 60


class PoseStabilityTracker:
    """滑动窗口位姿稳定性统计。

    指标:
      t_std:  平移各轴标准差 (mm) — 越小越稳定
      t_ptp:  平移各轴峰峰值 (mm) — 最大跳动范围
      r_std:  旋转各轴标准差 (deg) — 越小越稳定
      r_ptp:  旋转各轴峰峰值 (deg) — 最大跳动范围
    """

    def __init__(self, window: int = 60):
        self._window = window
        self._tvecs: list[np.ndarray] = []   # 每帧的 (3,) tvec
        self._rvecs: list[np.ndarray] = []   # 每帧的 (3,) rvec (转欧拉后)

    def push(self, tvec: np.ndarray, rvec: np.ndarray):
        """添加一帧位姿样本。tvec: (3,1) or (3,), rvec: (3,1) or (3,)"""
        self._tvecs.append(np.asarray(tvec).ravel().copy())
        r_flat = np.asarray(rvec).ravel()
        # rvec → 欧拉角 (使用 Rodrigues)
        R, _ = cv2.Rodrigues(r_flat)
        euler = _rotmat_to_euler(R)
        self._rvecs.append(np.array(euler))
        # 保持窗口大小
        while len(self._tvecs) > self._window:
            self._tvecs.pop(0)
            self._rvecs.pop(0)

    @property
    def ready(self) -> bool:
        return len(self._tvecs) >= 5

    @property
    def stats(self) -> dict:
        """返回统计指标字典。"""
        if len(self._tvecs) < 3:
            return {"samples": len(self._tvecs)}
        t = np.array(self._tvecs)  # (N, 3) 单位: m
        r = np.array(self._rvecs)  # (N, 3) 单位: deg
        return {
            "samples": len(self._tvecs),
            # 平移 (mm)
            "t_std": tuple(float(v) for v in np.std(t, axis=0) * 1000),
            "t_ptp": tuple(float(v) for v in (np.max(t, axis=0) - np.min(t, axis=0)) * 1000),
            # 旋转 (deg)
            "r_std": tuple(float(v) for v in np.std(r, axis=0)),
            "r_ptp": tuple(float(v) for v in (np.max(r, axis=0) - np.min(r, axis=0))),
        }

    def reset(self):
        self._tvecs.clear()
        self._rvecs.clear()


def _rotmat_to_euler(R: np.ndarray) -> tuple[float, float, float]:
    """旋转矩阵 → xyz 欧拉角 (roll, pitch, yaw), 纯 numpy"""
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

# 相机内参 (来自 camera_config.yaml right_arm 标定结果)
CAMERA_MATRIX = np.array([
    [608.3646, 0,       643.3548],
    [0,        608.3131, 362.1399],
    [0,        0,       1],
], dtype=np.float64)
DIST_COEFFS = np.array([-0.02938, 0.03325, -0.00044, 0.00003, -0.01179], dtype=np.float64)


def _color_frame_to_bgr(frame):
    fmt = frame.get_format()
    w, h = frame.get_width(), frame.get_height()
    raw = np.frombuffer(frame.get_data(), dtype=np.uint8)

    if fmt == OBFormat.MJPG:
        return cv2.imdecode(raw, cv2.IMREAD_COLOR)
    elif fmt == OBFormat.NV21:
        mat = raw.reshape((h * 3 // 2, w))
        return cv2.cvtColor(mat, cv2.COLOR_YUV2BGR_NV21)
    elif fmt in (OBFormat.YUYV, OBFormat.YUY2):
        mat = raw.reshape((h, w, 2))
        return cv2.cvtColor(mat, cv2.COLOR_YUV2BGR_YUY2)
    elif fmt == OBFormat.RGB:
        mat = raw.reshape((h, w, 3))
        return cv2.cvtColor(mat, cv2.COLOR_RGB2BGR)
    elif fmt == OBFormat.UYVY:
        mat = raw.reshape((h, w, 2))
        return cv2.cvtColor(mat, cv2.COLOR_YUV2BGR_UYVY)
    elif fmt == OBFormat.BGR:
        return raw.reshape((h, w, 3)).copy()
    return None


def _ir_frame_to_gray(frame):
    fmt = frame.get_format()
    w, h = frame.get_width(), frame.get_height()
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
    elif fmt == OBFormat.Y10:
        unpacked = np.zeros(h * w, dtype=np.uint16)
        for i in range(0, h * w, 4):
            base = i * 5 // 4
            if base + 4 < len(raw):
                unpacked[i] = int(raw[base]) | ((int(raw[base + 1]) & 0x03) << 8)
                unpacked[i + 1] = ((int(raw[base + 1]) >> 2) |
                                   ((int(raw[base + 2]) & 0x0F) << 6))
                unpacked[i + 2] = ((int(raw[base + 2]) >> 4) |
                                   ((int(raw[base + 3]) & 0x3F) << 4))
                unpacked[i + 3] = ((int(raw[base + 3]) >> 6) |
                                   (int(raw[base + 4]) << 2))
        gray = (unpacked.reshape((h, w)) >> 2).astype(np.uint8)
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


def _draw_qr_overlay(image: np.ndarray, results: list,
                     detector: QRDetector) -> np.ndarray:
    """
    绘制检测框、坐标轴、旋转矩阵和平移向量。
    使用 QRDetector.draw_results() 绘制基础标注，
    再叠加旋转矩阵文字。
    """
    # 先用模块自带的可视化 (检测框 + 坐标轴 + tvec 文字)
    out = detector.draw_results(image, results, axis_length=0.04)

    # 再叠加旋转矩阵
    for r in results:
        R, _ = cv2.Rodrigues(r.rvec)
        cx = int(r.corners[0, 0, 0])
        cy = int(r.corners[0, 0, 1]) + 16  # draw_results 写了 tvec, 往下写 R

        highlight = (r.qr_id == QR_TARGET_ID)
        color = (0, 255, 255) if highlight else (200, 200, 200)
        thick = 2 if highlight else 1

        r_lines = [
            f"R=[{R[0,0]:.4f},{R[0,1]:.4f},{R[0,2]:.4f}]",
            f"   [{R[1,0]:.4f},{R[1,1]:.4f},{R[1,2]:.4f}]",
            f"   [{R[2,0]:.4f},{R[2,1]:.4f},{R[2,2]:.4f}]",
        ]
        for j, line in enumerate(r_lines):
            cv2.putText(out, line, (cx, cy + j * 12), cv2.FONT_HERSHEY_SIMPLEX,
                        0.35, color, thick)

    return out


# ---- 初始化 ----
print(f"QR 检测器: {QR_DICT_NAME}, marker_size={QR_MARKER_SIZE}m, target_id={QR_TARGET_ID}")
print(f"相机内参: fx={CAMERA_MATRIX[0,0]:.2f} fy={CAMERA_MATRIX[1,1]:.2f}")

qr_detector = QRDetector(CAMERA_MATRIX, DIST_COEFFS)

ctx = Context()
ctx.set_logger_level(OBLogLevel.ERROR)
dl = ctx.query_devices()
if dl.get_count() == 0:
    print("未发现相机")
    sys.exit(1)

device = dl.get_device_by_index(0)
print(f"设备: {device.get_device_info().get_name()} "
      f"serial={device.get_device_info().get_serial_number()}")

pipeline = Pipeline(device)
config = Config()

# ---- COLOR 流 ----
try:
    color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
    color_profile = color_profiles.get_video_stream_profile(
        COLOR_WIDTH, COLOR_HEIGHT, OBFormat.RGB, COLOR_FPS)
except Exception:
    color_profile = color_profiles.get_video_stream_profile(
        COLOR_WIDTH, COLOR_HEIGHT, OBFormat.UNKNOWN, COLOR_FPS)
print(f"COLOR: {color_profile.get_width()}x{color_profile.get_height()} "
      f"fmt={color_profile.get_format()}")
if device.is_property_supported(OBPropertyID.OB_PROP_COLOR_MIRROR_BOOL,
                                OBPermissionType.PERMISSION_WRITE):
    device.set_bool_property(OBPropertyID.OB_PROP_COLOR_MIRROR_BOOL, FLIP)
config.enable_stream(color_profile)

# ---- DEPTH 流 ----
try:
    depth_profiles = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
    depth_profile = depth_profiles.get_video_stream_profile(
        DEPTH_WIDTH, DEPTH_HEIGHT, OBFormat.Y16, DEPTH_FPS)
except Exception:
    depth_profile = depth_profiles.get_video_stream_profile(
        DEPTH_WIDTH, DEPTH_HEIGHT, OBFormat.UNKNOWN, DEPTH_FPS)
print(f"DEPTH: {depth_profile.get_width()}x{depth_profile.get_height()} "
      f"fmt={depth_profile.get_format()}")
if device.is_property_supported(OBPropertyID.OB_PROP_DEPTH_MIRROR_BOOL,
                                OBPermissionType.PERMISSION_WRITE):
    device.set_bool_property(OBPropertyID.OB_PROP_DEPTH_MIRROR_BOOL, FLIP)
config.enable_stream(depth_profile)

# ---- IR 流 ----
try:
    ir_profiles = pipeline.get_stream_profile_list(OBSensorType.IR_SENSOR)
    ir_profile = ir_profiles.get_video_stream_profile(
        IR_WIDTH, IR_HEIGHT, OBFormat.Y8, IR_FPS)
except Exception:
    ir_profile = ir_profiles.get_video_stream_profile(
        IR_WIDTH, IR_HEIGHT, OBFormat.UNKNOWN, IR_FPS)
print(f"IR: {ir_profile.get_width()}x{ir_profile.get_height()} "
      f"fmt={ir_profile.get_format()}")
if device.is_property_supported(OBPropertyID.OB_PROP_IR_MIRROR_BOOL,
                                OBPermissionType.PERMISSION_WRITE):
    device.set_bool_property(OBPropertyID.OB_PROP_IR_MIRROR_BOOL, FLIP)
config.enable_stream(ir_profile)

# ---- 硬件对齐 ----
try:
    if device.is_property_supported(OBPropertyID.OB_PROP_DEPTH_ALIGN_HARDWARE_BOOL,
                                    OBPermissionType.PERMISSION_READ):
        config.set_align_mode(2)
        print("对齐: 硬件 D2C")
    else:
        config.set_align_mode(1)
        print("对齐: 软件 D2C")
except Exception:
    print("对齐: 不支持, 跳过")

# ---- 启动 ----
pipeline.start(config)
print("Pipeline 已启动 (COLOR + IR + DEPTH)\n")

# ---- 显示窗口 ----
cv2.namedWindow("Color QR", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Color QR", 640, 480)
cv2.namedWindow("IR QR", cv2.WINDOW_NORMAL)
cv2.resizeWindow("IR QR", 640, 480)

print(f"显示: Color QR 检测 / IR QR 检测")
print(f"{QR_DICT_NAME} | marker={QR_MARKER_SIZE*100:.0f}cm | 目标ID={QR_TARGET_ID}(高亮)")
print(f"稳定性统计: 窗口={STABILITY_WINDOW}帧 | t_std(mm) t_ptp(mm) r_std(deg) r_ptp(deg)")
print("检测模块: qr_detector.QRDetector (直接导入, 修改同步到控制系统)")
print("按 q 或 ESC 退出\n")

# ---- 稳定性跟踪器 (按目标 ID 跟踪) ----
_tracker_color = PoseStabilityTracker(STABILITY_WINDOW)
_tracker_ir = PoseStabilityTracker(STABILITY_WINDOW)

_debug_printed = False

while True:
    frames = pipeline.wait_for_frames(100)
    if frames is None:
        continue

    # ---- Color QR 检测 ----
    cf = frames.get_color_frame()
    if cf is not None:
        color_img = _color_frame_to_bgr(cf)
        if color_img is not None:
            results = qr_detector.detect(color_img, QR_MARKER_SIZE)
            color_disp = _draw_qr_overlay(color_img, results, qr_detector)

            count = len(results)
            target_hit = any(r.qr_id == QR_TARGET_ID for r in results)
            status = f"COLOR | found:{count}" + (" TARGET!" if target_hit else "")
            cv2.putText(color_disp, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (0, 255, 0) if count > 0 else (0, 0, 255), 2)

            # 稳定性统计
            target = next((r for r in results if r.qr_id == QR_TARGET_ID), None)
            if target:
                _tracker_color.push(target.tvec, target.rvec)
            if _tracker_color.ready:
                s = _tracker_color.stats
                st_lines = [
                    f"t_std:[{s['t_std'][0]:.2f},{s['t_std'][1]:.2f},{s['t_std'][2]:.2f}]mm",
                    f"t_ptp:[{s['t_ptp'][0]:.2f},{s['t_ptp'][1]:.2f},{s['t_ptp'][2]:.2f}]mm",
                    f"r_std:[{s['r_std'][0]:.2f},{s['r_std'][1]:.2f},{s['r_std'][2]:.2f}]deg",
                    f"r_ptp:[{s['r_ptp'][0]:.2f},{s['r_ptp'][1]:.2f},{s['r_ptp'][2]:.2f}]deg",
                ]
                for j, line in enumerate(st_lines):
                    cv2.putText(color_disp, line, (10, 55 + j * 16),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 200, 50), 1)

            cv2.imshow("Color QR", color_disp)

    # ---- IR QR 检测 ----
    ir_frame = frames.get_ir_frame()
    if ir_frame is None:
        ir_frame = frames.get_left_ir_frame() if hasattr(frames, "get_left_ir_frame") else None
    if ir_frame is None:
        ir_frame = frames.get_right_ir_frame() if hasattr(frames, "get_right_ir_frame") else None

    if not _debug_printed:
        _debug_printed = True
        available = []
        for name in ["get_color_frame", "get_depth_frame", "get_ir_frame",
                      "get_left_ir_frame", "get_right_ir_frame"]:
            if hasattr(frames, name):
                f = getattr(frames, name)()
                if f is not None:
                    available.append(f"{name}()={f.get_width()}x{f.get_height()} fmt={f.get_format()}")
                else:
                    available.append(f"{name}()=None")
        print(f"[DEBUG] frameset 可用帧: {available}")

    if ir_frame is not None:
        ir_gray = _ir_frame_to_gray(ir_frame)
        if ir_gray is not None and ir_gray.max() > 0:
            results = qr_detector.detect(ir_gray, QR_MARKER_SIZE)
            ir_disp = _draw_qr_overlay(ir_gray, results, qr_detector)

            count = len(results)
            target_hit = any(r.qr_id == QR_TARGET_ID for r in results)
            status = f"IR | found:{count}" + (" TARGET!" if target_hit else "")
            cv2.putText(ir_disp, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                        0.55, (0, 255, 0) if count > 0 else (0, 0, 255), 2)

            # 稳定性统计
            target = next((r for r in results if r.qr_id == QR_TARGET_ID), None)
            if target:
                _tracker_ir.push(target.tvec, target.rvec)
            if _tracker_ir.ready:
                s = _tracker_ir.stats
                st_lines = [
                    f"t_std:[{s['t_std'][0]:.2f},{s['t_std'][1]:.2f},{s['t_std'][2]:.2f}]mm",
                    f"t_ptp:[{s['t_ptp'][0]:.2f},{s['t_ptp'][1]:.2f},{s['t_ptp'][2]:.2f}]mm",
                    f"r_std:[{s['r_std'][0]:.2f},{s['r_std'][1]:.2f},{s['r_std'][2]:.2f}]deg",
                    f"r_ptp:[{s['r_ptp'][0]:.2f},{s['r_ptp'][1]:.2f},{s['r_ptp'][2]:.2f}]deg",
                ]
                for j, line in enumerate(st_lines):
                    cv2.putText(ir_disp, line, (10, 55 + j * 16),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 200, 50), 1)

            cv2.imshow("IR QR", ir_disp)

    key = cv2.waitKey(1)
    if key == ord("q") or key == 27:
        break

cv2.destroyAllWindows()
try:
    pipeline.stop()
except Exception:
    pass
print("Done")

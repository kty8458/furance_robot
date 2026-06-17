#!/usr/bin/env python3
"""
IR 红外流棋盘格识别测试
适配自 Orbbec C++ IR 示例 (frame2mat)，使用 pyorbbecsdk Python SDK。
同时开启 COLOR + IR + DEPTH 三路流，硬件对齐。
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
import numpy as np
from pyorbbecsdk import (
    Context, Config, OBLogLevel, OBSensorType,
    Pipeline, OBFormat, OBFrameType,
    OBPropertyID, OBPermissionType,
)

# ---- 配置 ----
IR_WIDTH, IR_HEIGHT, IR_FPS = 640, 0, 30
COLOR_WIDTH, COLOR_HEIGHT, COLOR_FPS = 640, 0, 30
DEPTH_WIDTH, DEPTH_HEIGHT, DEPTH_FPS = 640, 0, 30
FLIP = False
CHESSBOARD_SIZE = (11, 8)


def _color_frame_to_bgr(frame):
    """适配自 C++ frame2mat COLOR 分支。用 np.frombuffer 兼容 pyorbbecsdk buffer。"""
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
    """
    适配自 C++ frame2mat IR / Y16 分支
    使用 np.frombuffer 而非 np.asanyarray (pyorbbecsdk buffer 兼容性更好)
    """
    fmt = frame.get_format()
    w, h = frame.get_width(), frame.get_height()
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
    elif fmt == OBFormat.Y10:
        # Y10 打包: 4 像素 = 5 字节
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
        return (unpacked.reshape((h, w)) >> 2).astype(np.uint8)
    elif fmt == OBFormat.MJPG:
        return cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
    return None


# ---- 初始化 ----
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

# ---- IR 流 (Y16, 与 C++ 示例一致) ----
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
        config.set_align_mode(2)  # ALIGN_D2C_HW_MODE
        print("对齐: 硬件 D2C")
    else:
        config.set_align_mode(1)  # ALIGN_D2C_SW_MODE
        print("对齐: 软件 D2C")
except Exception:
    print("对齐: 不支持, 跳过")

# ---- 启动 ----
pipeline.start(config)
print("Pipeline 已启动 (COLOR + IR + DEPTH)\n")

# ---- 显示窗口 ----
cv2.namedWindow("Color Chessboard", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Color Chessboard", 640, 480)
# cv2.namedWindow("Depth", cv2.WINDOW_NORMAL)
# cv2.resizeWindow("Depth", 640, 480)
# cv2.namedWindow("IR", cv2.WINDOW_NORMAL)
# cv2.resizeWindow("IR", 640, 480)
cv2.namedWindow("IR Chessboard", cv2.WINDOW_NORMAL)
cv2.resizeWindow("IR Chessboard", 640, 480)

print("显示: Color / Depth / IR / IR棋盘格")
print("按 q 或 ESC 退出\n")

_debug_printed = False

while True:
    frames = pipeline.wait_for_frames(100)
    if frames is None:
        continue

    # ---- Color ----
    cf = frames.get_color_frame()
    if cf is not None:
        color_img = _color_frame_to_bgr(cf)
        if color_img is not None:
            # color_img 已是 BGR (3通道), 直接用于检测和显示
            sb_flags = cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_NORMALIZE_IMAGE
            gray_for_cb = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)
            ret, corners = cv2.findChessboardCornersSB(
                gray_for_cb, CHESSBOARD_SIZE, sb_flags)
            if not ret:
                ret, corners = cv2.findChessboardCorners(
                    gray_for_cb, CHESSBOARD_SIZE,
                    cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)

            color_cb = color_img.copy()
            if ret:
                cv2.drawChessboardCorners(color_cb, CHESSBOARD_SIZE, corners, ret)

            status = f"COLOR {'OK' if ret else 'no board'}"
            cv2.putText(color_cb, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 0) if ret else (0, 0, 255), 2)
            cv2.imshow("Color Chessboard", color_cb)
    # # ---- Depth ----
    # df = frames.get_depth_frame()
    # if df is not None:
    #     depth_gray = _ir_frame_to_gray(df)
    #     if depth_gray is not None:
    #         depth_display = cv2.applyColorMap(depth_gray, cv2.COLORMAP_JET)
    #         cv2.imshow("Depth", depth_display)

    # ---- IR (LEFT_IR_FRAME) ----
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
            # IR 棋盘格检测
            sb_flags = cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_NORMALIZE_IMAGE
            ret, corners = cv2.findChessboardCornersSB(ir_gray, CHESSBOARD_SIZE, sb_flags)
            if not ret:
                ret, corners = cv2.findChessboardCorners(
                    ir_gray, CHESSBOARD_SIZE,
                    cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)

            ir_cb = cv2.cvtColor(ir_gray, cv2.COLOR_GRAY2BGR)
            if ret:
                cv2.drawChessboardCorners(ir_cb, CHESSBOARD_SIZE, corners, ret)

            status = f"IR {'OK' if ret else 'no board'}"
            cv2.putText(ir_cb, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 0) if ret else (0, 0, 255), 2)
            cv2.imshow("IR Chessboard", ir_cb)

    key = cv2.waitKey(1)
    if key == ord("q") or key == 27:  # q 或 ESC
        break

cv2.destroyAllWindows()
try:
    pipeline.stop()
except Exception:
    pass
print("Done")

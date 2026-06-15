#!/usr/bin/env python3
"""
奥比中光 (Orbbec) 相机示例 — 获取摄像头信息 + 彩色/深度视频流显示

功能:
  1. 发现并打印已连接相机的设备信息（名称、序列号、固件版本等）
  2. 枚举默认 Color / Depth 流配置
  3. 显示当前深度预设及可用预设列表
  4. 启动 Color + Depth 双流，左右并排显示彩色图像和深度图

依赖:
  pip install pyorbbecsdk opencv-python numpy

运行:
  python orbbec_camera_example.py

控制:
  Q / ESC — 退出
"""

import os
import sys
import time

# ---------------------------------------------------------------------------
# 修复 LD_LIBRARY_PATH: pyorbbecsdk pip 包自带的 libOrbbecSDK (v2.8.6)
# 必须优先于 ROS2 自带的旧版 (v2.7.6)，否则会出现 undefined symbol 错误。
# 由于动态链接器在进程启动时就已解析库路径，运行时修改 LD_LIBRARY_PATH
# 无效——这里用 execve 重启自身，在新环境中重新执行。
# ---------------------------------------------------------------------------
_SDK_LIB_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "lib", "python3.10",
    "site-packages", "pyorbbecsdk",
)
if os.path.isdir(_SDK_LIB_DIR):
    _current_ld = os.environ.get("LD_LIBRARY_PATH", "")
    _paths = _current_ld.split(":") if _current_ld else []
    if _SDK_LIB_DIR not in _paths:
        os.environ["LD_LIBRARY_PATH"] = _SDK_LIB_DIR + ":" + _current_ld if _current_ld else _SDK_LIB_DIR
        print("⚠️  LD_LIBRARY_PATH 已修正，重启脚本以加载正确的 libOrbbecSDK 版本...")
        os.execve(sys.executable, [sys.executable] + sys.argv, os.environ)

import cv2
import numpy as np

from pyorbbecsdk import (
    Config,
    Context,
    OBError,
    OBFormat,
    OBLogLevel,
    OBSensorType,
    Pipeline,
)

# ---------------------------------------------------------------------------
# 深度渲染配置
# ---------------------------------------------------------------------------
MIN_DEPTH_MM = 100       # 深度裁剪下限 (mm)
MAX_DEPTH_MM = 5000      # 深度裁剪上限 (mm)
WINDOW_NAME = "Orbbec Camera — Color + Depth  |  Q / ESC = quit"


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def frame_to_bgr_image(frame):
    """
    将 SDK VideoFrame 转换为 OpenCV BGR numpy 数组。

    支持 RGB / BGR / YUYV / MJPG / I420 / NV12 / NV21 / UYVY 格式。
    """
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
        print(f"Unsupported color format: {fmt}")
        return None


def render_depth_3d(depth_mm: np.ndarray) -> np.ndarray:
    """
    将 float32 深度图 (mm) 渲染为带 3D 浮雕光照的 BGR 图像。

    流程: clip → gamma 0.8 → uint8 → Scharr 梯度光照 → JET colormap
    """
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


# ---------------------------------------------------------------------------
# 第 1 部分: 打印摄像头信息
# ---------------------------------------------------------------------------

def print_device_info():
    """发现并打印所有已连接 Orbbec 相机的详细信息。"""
    ctx = Context()
    ctx.set_logger_level(OBLogLevel.WARNING)

    device_list = ctx.query_devices()
    count = device_list.get_count()

    if count == 0:
        print("未发现 Orbbec 设备！请检查:")
        print("  - 相机是否已通过 USB 连接")
        print("  - 当前用户是否在 plugdev 组: sudo usermod -aG plugdev $USER")
        return None

    print(f"\n发现 {count} 个设备:\n")

    for i in range(count):
        device = device_list.get_device_by_index(i)
        info = device.get_device_info()

        print(f"{'='*60}")
        print(f"  设备 #{i + 1}")
        print(f"{'='*60}")
        print(f"  名称           : {info.get_name()}")
        print(f"  序列号         : {info.get_serial_number()}")
        print(f"  固件版本       : {info.get_firmware_version()}")
        print(f"  硬件版本       : {info.get_hardware_version()}")
        print(f"  USB PID / VID  : 0x{info.get_pid():04X} / 0x{info.get_vid():04X}")
        print(f"  连接类型       : {info.get_connection_type()}")
        print()

        # 枚举默认 Color / Depth 流配置
        pipeline = Pipeline(device)

        SENSOR_TYPES = [
            (OBSensorType.COLOR_SENSOR, "Color"),
            (OBSensorType.DEPTH_SENSOR, "Depth"),
        ]

        print("  默认流配置:")
        for sensor_type, label in SENSOR_TYPES:
            try:
                profiles = pipeline.get_stream_profile_list(sensor_type)
                p = profiles.get_default_video_stream_profile()
                print(
                    f"    {label:<8} : {p.get_width()}x{p.get_height()}"
                    f" @ {p.get_fps()} fps  format={p.get_format()}"
                )
            except OBError:
                print(f"    {label:<8} : (不可用)")

        # 深度预设
        print()
        print("  深度预设:")
        try:
            current = device.get_current_preset_name()
            print(f"    当前预设  : {current}")
            preset_list = device.get_available_preset_list()
            names = [preset_list[j] for j in range(len(preset_list))]
            print(f"    可用预设  : {', '.join(names)}")
        except OBError:
            print("    (该设备不支持预设)")

        print()

    return device_list


# ---------------------------------------------------------------------------
# 第 2 部分: 彩色 + 深度视频流显示
# ---------------------------------------------------------------------------

def run_stream_viewer():
    """启动 Color + Depth 双流，左右并排显示彩色图像和深度图。"""
    pipeline = Pipeline()

    config = Config()
    try:
        # 启用默认 Color 流
        color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        color_profile = color_profiles.get_default_video_stream_profile()
        print(f"Color  流: {color_profile.get_width()}x{color_profile.get_height()}"
              f" @ {color_profile.get_fps()} fps  format={color_profile.get_format()}")
        config.enable_stream(color_profile)

        # 启用默认 Depth 流
        depth_profiles = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
        depth_profile = depth_profiles.get_default_video_stream_profile()
        print(f"Depth  流: {depth_profile.get_width()}x{depth_profile.get_height()}"
              f" @ {depth_profile.get_fps()} fps  format={depth_profile.get_format()}")
        config.enable_stream(depth_profile)
    except OBError as e:
        print(f"流配置失败: {e}")
        return

    try:
        pipeline.start(config)
    except OBError as e:
        print(f"Pipeline 启动失败: {e}")
        print("请确认相机未被其他进程占用。")
        return

    print(f"\nPipeline 已启动。深度范围: {MIN_DEPTH_MM} – {MAX_DEPTH_MM} mm")
    print("按 Q 或 ESC 退出。\n")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1280, 480)

    # FPS 统计
    frame_count = 0
    fps_start = time.time()
    fps_text = "FPS: --"

    try:
        while True:
            frames = pipeline.wait_for_frames(1000)
            if frames is None:
                continue

            # ---- 获取彩色帧 ----
            color_frame = frames.get_color_frame()
            if color_frame is None:
                continue
            color_image = frame_to_bgr_image(color_frame)
            if color_image is None:
                continue

            # ---- 获取深度帧 ----
            depth_frame = frames.get_depth_frame()
            if depth_frame is None:
                continue

            width = depth_frame.get_width()
            height = depth_frame.get_height()
            scale = depth_frame.get_depth_scale()

            depth_data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
            depth_data = depth_data.reshape((height, width))
            depth_mm = depth_data.astype(np.float32) * scale

            # ---- 渲染深度图 ----
            depth_image = render_depth_3d(depth_mm)

            # ---- 深度图中心点距离标注 ----
            cy, cx = height // 2, width // 2
            center_dist = depth_mm[cy, cx]
            if MIN_DEPTH_MM <= center_dist <= MAX_DEPTH_MM:
                dist_label = f"{center_dist:.0f} mm"
                cv2.circle(depth_image, (cx, cy), 5, (255, 255, 255), -1)
                cv2.putText(depth_image, dist_label, (cx + 8, cy + 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            # ---- 深度范围图例 ----
            cv2.putText(depth_image, f"{MIN_DEPTH_MM} – {MAX_DEPTH_MM} mm",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # ---- FPS 统计 ----
            frame_count += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                fps_text = f"FPS: {frame_count / elapsed:.1f}"
                frame_count = 0
                fps_start = time.time()

            # ---- 并排显示 ----
            target_h = 480
            color_resized = cv2.resize(color_image,
                                       (int(color_image.shape[1] * target_h / color_image.shape[0]), target_h))
            depth_resized = cv2.resize(depth_image,
                                       (int(depth_image.shape[1] * target_h / depth_image.shape[0]), target_h))

            combined = np.hstack((color_resized, depth_resized))

            # FPS 叠加
            cv2.putText(combined, fps_text, (10, combined.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            cv2.imshow(WINDOW_NAME, combined)

            key = cv2.waitKey(1)
            if key in (ord("q"), ord("Q"), 27):  # 27 = ESC
                break

    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
        print("Pipeline 已停止。")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    # ---- 第 1 步: 打印摄像头信息 ----
    print_device_info()

    # ---- 第 2 步: 启动视频流显示 ----
    print("\n启动彩色 + 深度视频流显示...")
    run_stream_viewer()


if __name__ == "__main__":
    main()

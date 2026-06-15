#!/usr/bin/env python3
"""
相机标定脚本 — 一次性运行，将标定结果写入 camera_config.yaml。

功能:
  1. 从 pyorbbecsdk 获取相机内参 (color + depth) 和畸变系数
  2. 从 SDK 获取 color→depth 外参变换
  3. 棋盘格标定: 计算 head_camera_link → ARM-R-J7_Link 的手眼变换
  4. 结果写入 camera_config.yaml 的 calibration 段

棋盘格固定在 ARM-R-J7_Link 上。标定时将棋盘格置于相机视野中，
脚本采集多帧图像，通过 OpenCV solvePnP 计算相机→棋盘格变换，
再结合已知的棋盘格→ARM-R-J7_Link 偏移得到最终变换。

用法:
  python3 camera_calibration.py \\
    --camera head \\
    --chessboard 9x6 \\
    --square 0.025 \\
    --target-link ARM-R-J7_Link

棋盘格参数:
  --chessboard: 内角点数 (宽x高), 默认 9x6
  --square:     方格边长 (米), 默认 0.025
  --frames:     采集帧数, 默认 20

依赖:
  pip install pyorbbecsdk opencv-python numpy pyyaml
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import yaml

# ---------------------------------------------------------------------------
# LD_LIBRARY_PATH
# ---------------------------------------------------------------------------
_SDK_LIB_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "lib", "python3.10",
    "site-packages", "pyorbbecsdk",
)
if os.path.isdir(_SDK_LIB_DIR):
    _ld = os.environ.get("LD_LIBRARY_PATH", "")
    if _SDK_LIB_DIR not in _ld.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{_SDK_LIB_DIR}:{_ld}" if _ld else _SDK_LIB_DIR
        os.execve(sys.executable, [sys.executable] + sys.argv, os.environ)

# ---------------------------------------------------------------------------
# 配置路径
# ---------------------------------------------------------------------------
_DEFAULT_CONFIG = Path(__file__).resolve().parent / "camera_config.yaml"


# ---------------------------------------------------------------------------
# SDK 内参 / 外参获取
# ---------------------------------------------------------------------------

def get_camera_params(serial: str) -> dict:
    """
    从 SDK 获取指定序列号相机的内参和外参。

    Returns:
        {
            "color_intrinsics": {fx, fy, cx, cy, width, height, distortion: [k1,k2,p1,p2,k3]},
            "depth_intrinsics": {...},
            "color_to_depth": {rotation: [r,p,y], translation: [x,y,z]},
        }
    """
    from pyorbbecsdk import Context, OBSensorType, Pipeline, OBLogLevel

    ctx = Context()
    ctx.set_logger_level(OBLogLevel.ERROR)
    device_list = ctx.query_devices()

    device = None
    for i in range(device_list.get_count()):
        d = device_list.get_device_by_index(i)
        info = d.get_device_info()
        if info.get_serial_number() == serial:
            device = d
            break

    if device is None:
        # 如果没找到匹配的 serial，取第一个设备
        if device_list.get_count() > 0:
            device = device_list.get_device_by_index(0)
            print(f"未找到 serial={serial} 的设备，使用第一个: "
                  f"{device.get_device_info().get_serial_number()}")
        else:
            raise RuntimeError("未发现奥比中光相机")

    pipeline = Pipeline(device)

    # --- Color 内参 ---
    color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
    cp = color_profiles.get_default_video_stream_profile()
    color_intr = cp.get_intrinsic()
    color_dist = cp.get_distortion() if hasattr(cp, "get_distortion") else None
    color_result = {
        "fx": color_intr.fx, "fy": color_intr.fy,
        "cx": color_intr.cx, "cy": color_intr.cy,
        "width": cp.get_width(), "height": cp.get_height(),
        "distortion": _distortion_to_list(color_dist),
    }

    # --- Depth 内参 ---
    depth_profiles = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
    dp = depth_profiles.get_default_video_stream_profile()
    depth_intr = dp.get_intrinsic()
    depth_dist = dp.get_distortion() if hasattr(dp, "get_distortion") else None
    depth_result = {
        "fx": depth_intr.fx, "fy": depth_intr.fy,
        "cx": depth_intr.cx, "cy": depth_intr.cy,
        "width": dp.get_width(), "height": dp.get_height(),
        "distortion": _distortion_to_list(depth_dist),
    }

    # --- Color→Depth 外参 ---
    try:
        extrin = cp.get_extrinsic_to(dp)
        c2d = _extrinsic_to_dict(extrin)
    except Exception:
        print("警告: 无法获取 color→depth 外参")
        c2d = {"rotation": [0, 0, 0], "translation": [0, 0, 0]}

    return {
        "color_intrinsics": color_result,
        "depth_intrinsics": depth_result,
        "color_to_depth": c2d,
    }


def _distortion_to_list(dist) -> list:
    """将 OBCameraDistortion 转为 [k1, k2, p1, p2, k3] 列表。"""
    if dist is None:
        return [0.0, 0.0, 0.0, 0.0, 0.0]
    try:
        return [dist.k1, dist.k2, dist.p1, dist.p2, dist.k3]
    except AttributeError:
        # 回退: 尝试 model 属性
        return [getattr(dist, "k1", 0.0), getattr(dist, "k2", 0.0),
                getattr(dist, "p1", 0.0), getattr(dist, "p2", 0.0),
                getattr(dist, "k3", 0.0)]


def _extrinsic_to_dict(extrin) -> dict:
    """将 OBExtrinsic 转为 rotation(rpy) + translation(xyz)。"""
    rot = extrin.rot  # 3x3 rotation matrix
    trans = extrin.transform[:3, 3] if hasattr(extrin, "transform") else np.zeros(3)
    rpy = _rotmat_to_rpy(rot)
    return {
        "rotation": [float(rpy[0]), float(rpy[1]), float(rpy[2])],
        "translation": [float(trans[0]), float(trans[1]), float(trans[2])],
    }


def _rotmat_to_rpy(R: np.ndarray) -> np.ndarray:
    """旋转矩阵 → RPY (roll, pitch, yaw)。"""
    sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        x = np.arctan2(R[2, 1], R[2, 2])
        y = np.arctan2(-R[2, 0], sy)
        z = np.arctan2(R[1, 0], R[0, 0])
    else:
        x = np.arctan2(-R[1, 2], R[1, 1])
        y = np.arctan2(-R[2, 0], sy)
        z = 0.0
    return np.array([x, y, z])


# ---------------------------------------------------------------------------
# 棋盘格标定
# ---------------------------------------------------------------------------

def _collect_chessboard_frames(
    pipeline, chessboard_size: Tuple[int, int], square_size: float,
    num_frames: int = 20,
) -> list:
    """
    采集 num_frames 帧有效棋盘格图像，返回 image_points 列表。

    每帧: 检测棋盘格内角点 → 记录角点坐标 (image_points)
    对应的世界坐标 (object_points) 由棋盘格几何计算。
    """
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    objp = np.zeros((chessboard_size[0] * chessboard_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:chessboard_size[0], 0:chessboard_size[1]].T.reshape(-1, 2)
    objp *= square_size

    obj_points = []
    img_points = []

    print(f"\n开始采集棋盘格图像 (需要 {num_frames} 帧)...")
    print("将棋盘格置于相机视野中不同位置/角度，按 's' 保存当前帧，按 'q' 退出")
    print(f"棋盘格: {chessboard_size[0]}x{chessboard_size[1]}, 方格: {square_size}m")

    cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Calibration", 1280, 720)

    captured = 0
    while captured < num_frames:
        frames = pipeline.wait_for_frames(1000)
        if frames is None:
            continue
        color_frame = frames.get_color_frame()
        if color_frame is None:
            continue

        img = _frame_to_bgr(color_frame)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, chessboard_size, None)

        display = img.copy()
        if ret:
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            cv2.drawChessboardCorners(display, chessboard_size, corners2, ret)
            status_text = f"检测成功 — 按 's' 保存 ({captured + 1}/{num_frames})"
        else:
            status_text = f"未检测到棋盘格 — 调整位置 ({captured + 1}/{num_frames})"

        cv2.putText(display, status_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if ret else (0, 0, 255), 2)
        cv2.imshow("Calibration", display)

        key = cv2.waitKey(1)
        if key == ord("q"):
            cv2.destroyAllWindows()
            sys.exit(0)
        elif key == ord("s") and ret:
            obj_points.append(objp)
            img_points.append(corners2)
            captured += 1
            print(f"  [{captured}/{num_frames}] 已保存")

        time.sleep(0.03)

    cv2.destroyAllWindows()
    print(f"采集完成: {captured} 帧\n")
    return obj_points, img_points


def _frame_to_bgr(frame) -> Optional[np.ndarray]:
    """SDK VideoFrame → BGR numpy。"""
    from pyorbbecsdk import OBFormat

    w, h = frame.get_width(), frame.get_height()
    fmt = frame.get_format()
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


def calibrate_hand_eye(
    camera_id: str,
    serial: str,
    chessboard_size: Tuple[int, int],
    square_size: float,
    target_link: str,
    num_frames: int = 20,
) -> dict:
    """
    执行手眼标定: 计算 camera → target_link 变换。

    流程:
      1. 启动 Pipeline, 获取 SDK 内参/外参
      2. 采集棋盘格图像 → solvePnP 计算 camera→chessboard
      3. 用户输入 chessboard→target_link 偏移
      4. 计算 camera→target_link 并写入配置
    """
    from pyorbbecsdk import Config, Context, OBLogLevel, OBSensorType, Pipeline

    # 获取 SDK 参数
    print("正在获取相机内参/外参...")
    sdk_params = get_camera_params(serial)
    print(f"  Color: {sdk_params['color_intrinsics']['width']}x"
          f"{sdk_params['color_intrinsics']['height']} "
          f"fx={sdk_params['color_intrinsics']['fx']:.1f}")
    print(f"  Depth: {sdk_params['depth_intrinsics']['width']}x"
          f"{sdk_params['depth_intrinsics']['height']} "
          f"fx={sdk_params['depth_intrinsics']['fx']:.1f}")

    # 启动 Pipeline 用于采集
    ctx = Context()
    ctx.set_logger_level(OBLogLevel.ERROR)
    dl = ctx.query_devices()

    device = None
    for i in range(dl.get_count()):
        d = dl.get_device_by_index(i)
        if d.get_device_info().get_serial_number() == serial:
            device = d
            break
    if device is None and dl.get_count() > 0:
        device = dl.get_device_by_index(0)

    if device is None:
        raise RuntimeError("未发现相机")

    pipeline = Pipeline(device)
    config = Config()
    config.enable_stream(
        pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        .get_default_video_stream_profile()
    )
    pipeline.start(config)
    print("Pipeline 已启动")

    try:
        # 采集棋盘格
        obj_points, img_points = _collect_chessboard_frames(
            pipeline, chessboard_size, square_size, num_frames,
        )

        # solvePnP 计算 camera→chessboard
        K = np.array([
            [sdk_params["color_intrinsics"]["fx"], 0, sdk_params["color_intrinsics"]["cx"]],
            [0, sdk_params["color_intrinsics"]["fy"], sdk_params["color_intrinsics"]["cy"]],
            [0, 0, 1],
        ])
        dist = np.array(sdk_params["color_intrinsics"]["distortion"][:5])

        print("正在计算 camera→chessboard 变换 (solvePnP)...")
        rvecs = []
        tvecs = []
        for obj_pts, img_pts in zip(obj_points, img_points):
            ret, rvec, tvec = cv2.solvePnP(obj_pts, img_pts, K, dist)
            if ret:
                rvecs.append(rvec)
                tvecs.append(tvec)

        if not rvecs:
            raise RuntimeError("solvePnP 失败，请重新标定")

        # 取最后一帧（用户最后确认的位置）
        rvec = rvecs[-1]
        tvec = tvecs[-1]
        R, _ = cv2.Rodrigues(rvec)
        rpy = _rotmat_to_rpy(R)

        print(f"\n相机 → 棋盘格 变换 (最后一帧):")
        print(f"  rotation (rpy): [{rpy[0]:.4f}, {rpy[1]:.4f}, {rpy[2]:.4f}]")
        print(f"  translation (m): [{tvec[0][0]:.4f}, {tvec[1][0]:.4f}, {tvec[2][0]:.4f}]")

        # 用户输入棋盘格→target_link 偏移
        print(f"\n棋盘格固定在 {target_link} 上。")
        print("请输入棋盘格坐标系原点相对于 {target_link} 原点的偏移:")
        try:
            cb_x = float(input("  X 偏移 (m): ").strip() or "0")
            cb_y = float(input("  Y 偏移 (m): ").strip() or "0")
            cb_z = float(input("  Z 偏移 (m): ").strip() or "0")
            cb_roll = float(input("  Roll (rad): ").strip() or "0")
            cb_pitch = float(input("  Pitch (rad): ").strip() or "0")
            cb_yaw = float(input("  Yaw (rad): ").strip() or "0")
        except (EOFError, KeyboardInterrupt):
            print("\n跳过手动输入，使用默认偏移 (0,0,0,0,0,0)")
            cb_x = cb_y = cb_z = cb_roll = cb_pitch = cb_yaw = 0.0

        # 计算 camera → target_link = camera→chessboard * chessboard→target_link
        # camera→chessboard 的逆
        T_cam_cb = np.eye(4)
        T_cam_cb[:3, :3] = R
        T_cam_cb[:3, 3] = tvec.flatten()

        # chessboard→target_link
        R_cb_tgt, _ = cv2.Rodrigues(np.array([cb_roll, cb_pitch, cb_yaw]))
        T_cb_tgt = np.eye(4)
        T_cb_tgt[:3, :3] = R_cb_tgt
        T_cb_tgt[:3, 3] = [cb_x, cb_y, cb_z]

        # camera→target_link = camera→chessboard * chessboard→target_link
        # 注意: 这里棋盘格坐标系在 target_link 坐标系中的位姿
        T_cam_tgt = T_cam_cb @ T_cb_tgt
        tgt_rpy = _rotmat_to_rpy(T_cam_tgt[:3, :3])

        result = {
            "rotation": [float(tgt_rpy[0]), float(tgt_rpy[1]), float(tgt_rpy[2])],
            "translation": [
                float(T_cam_tgt[0, 3]), float(T_cam_tgt[1, 3]), float(T_cam_tgt[2, 3]),
            ],
        }

        print(f"\n相机 → {target_link} 变换:")
        print(f"  rotation (rpy): [{result['rotation'][0]:.4f}, "
              f"{result['rotation'][1]:.4f}, {result['rotation'][2]:.4f}]")
        print(f"  translation (m): [{result['translation'][0]:.4f}, "
              f"{result['translation'][1]:.4f}, {result['translation'][2]:.4f}]")

        return result

    finally:
        pipeline.stop()


# ---------------------------------------------------------------------------
# 写入 camera_config.yaml
# ---------------------------------------------------------------------------

def write_calibration_to_config(
    camera_id: str,
    sdk_params: dict,
    hand_eye: dict,
    target_link: str,
    config_path: str,
):
    """将标定结果写入 camera_config.yaml。"""
    path = Path(config_path)
    if path.exists():
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    cameras = data.get("cameras", [])
    target = None
    for cam in cameras:
        if cam.get("id") == camera_id:
            target = cam
            break

    if target is None:
        target = {"id": camera_id}
        cameras.append(target)
        data["cameras"] = cameras

    target["calibration"] = {
        "color_intrinsics": sdk_params["color_intrinsics"],
        "depth_intrinsics": sdk_params["depth_intrinsics"],
        "color_to_depth": sdk_params["color_to_depth"],
        f"camera_to_{target_link}": hand_eye,
    }

    # 保留 YAML 格式: 使用块风格
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\n标定结果已写入: {path}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="奥比中光相机标定")
    parser.add_argument("--camera", default="head", help="相机 ID (对应 camera_config.yaml)")
    parser.add_argument("--serial", default="", help="相机序列号 (不指定则使用配置中的)")
    parser.add_argument("--chessboard", default="9x6", help="棋盘格内角点数 (宽x高)")
    parser.add_argument("--square", type=float, default=0.025, help="方格边长 (米)")
    parser.add_argument("--target-link", default="ARM-R-J7_Link",
                        help="棋盘格所在的目标连杆名")
    parser.add_argument("--frames", type=int, default=20, help="采集帧数")
    parser.add_argument("--config", default=str(_DEFAULT_CONFIG),
                        help="camera_config.yaml 路径")
    args = parser.parse_args()

    # 解析棋盘格尺寸
    parts = args.chessboard.split("x")
    chessboard_size = (int(parts[0]), int(parts[1]))

    # 获取 serial
    serial = args.serial
    if not serial:
        # 从配置文件中读取
        try:
            with open(args.config, "r") as f:
                data = yaml.safe_load(f) or {}
            for cam in data.get("cameras", []):
                if cam.get("id") == args.camera:
                    serial = cam.get("serial", "")
                    break
        except FileNotFoundError:
            pass
    if not serial:
        print("未指定 serial，将使用第一个已连接相机")

    # 1. 获取 SDK 内参/外参
    print("=" * 60)
    print("步骤 1: 获取相机内参/外参")
    print("=" * 60)
    sdk_params = get_camera_params(serial)
    print(f"  Color 内参: fx={sdk_params['color_intrinsics']['fx']:.1f}, "
          f"fy={sdk_params['color_intrinsics']['fy']:.1f}, "
          f"cx={sdk_params['color_intrinsics']['cx']:.1f}, "
          f"cy={sdk_params['color_intrinsics']['cy']:.1f}")
    print(f"  Depth 内参: fx={sdk_params['depth_intrinsics']['fx']:.1f}, "
          f"fy={sdk_params['depth_intrinsics']['fy']:.1f}, "
          f"cx={sdk_params['depth_intrinsics']['cx']:.1f}, "
          f"cy={sdk_params['depth_intrinsics']['cy']:.1f}")
    print(f"  Color→Depth 外参: "
          f"r={sdk_params['color_to_depth']['rotation']}, "
          f"t={sdk_params['color_to_depth']['translation']}")

    # 2. 棋盘格标定
    print(f"\n{'=' * 60}")
    print(f"步骤 2: 棋盘格标定 (camera → {args.target_link})")
    print(f"{'=' * 60}")
    hand_eye = calibrate_hand_eye(
        camera_id=args.camera,
        serial=serial,
        chessboard_size=chessboard_size,
        square_size=args.square,
        target_link=args.target_link,
        num_frames=args.frames,
    )

    # 3. 写入配置
    print(f"\n{'=' * 60}")
    print("步骤 3: 写入 camera_config.yaml")
    print(f"{'=' * 60}")
    write_calibration_to_config(
        camera_id=args.camera,
        sdk_params=sdk_params,
        hand_eye=hand_eye,
        target_link=args.target_link,
        config_path=args.config,
    )

    print("\n标定完成!")


if __name__ == "__main__":
    main()

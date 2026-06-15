#!/usr/bin/env python3
"""
相机标定脚本 — Tsai AX=XB 手眼标定 (移植自 xjbd/eye_in_hand_calibration.cpp)。

功能:
  1. 从 pyorbbecsdk 获取相机内参 (color + depth) 和畸变系数
  2. 从 SDK 获取 color→depth 外参变换
  3. 棋盘格标定: 采集多帧 + solvePnP → camera→chessboard
  4. Tsai AX=XB 求解 camera→target_link 变换
  5. 结果写入 camera_config.yaml

标定场景 (eye-to-hand, 固定相机):
  - 相机固定在机器人头部 (head_camera_link)
  - 棋盘格固定在 ARM-R-J7_Link 上
  - 移动手臂到不同姿态，每帧记录:
    (a) arm 末端位姿 (base→target_link) — 从 pose.txt 或手动输入
    (b) 相机→棋盘格 (solvePnP)

Tsai 方程:
  令 A_ij = inv(base→target_link_i) * base→target_link_j    (已知: 手臂运动)
  令 B_ij = camera→chessboard_j * inv(camera→chessboard_i)   (已知: 观测)
  求解 AX=XB 得到 X = target_link→chessboard                 (未知常量)
  则 camera→target_link = camera→chessboard_i * inv(X)

用法:
  python3 camera_calibration.py \\
    --camera head \\
    --chessboard 9x6 \\
    --square 0.025 \\
    --target-link ARM-R-J7_Link \\
    --pose-file poses.txt

pose.txt 格式 (每行一个姿态):
  x y z roll pitch yaw
  (xyz 单位: 米, rpy 单位: 度)
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

_DEFAULT_CONFIG = Path(__file__).resolve().parent / "camera_config.yaml"


# ===================================================================
# Tsai AX=XB 手眼标定算法 (移植自 xjbd eye_in_hand_calibration.cpp)
# ===================================================================

def skew(v: np.ndarray) -> np.ndarray:
    """3x1 向量 → 3x3 反对称矩阵。"""
    return np.array([
        [0, -v[2], v[1]],
        [v[2], 0, -v[0]],
        [-v[1], v[0], 0],
    ])


def quat2rot(q: np.ndarray) -> np.ndarray:
    """3x1 单位四元数 (sin(θ/2)*axis) → 3x3 旋转矩阵。"""
    p = q @ q
    if p > 1:
        p = 1.0
    w = np.sqrt(1 - p)
    R = 2 * np.outer(q, q) + 2 * w * skew(q) + np.eye(3) - 2 * p * np.eye(3)
    return R


def rot2quat(R: np.ndarray) -> np.ndarray:
    """3x3 旋转矩阵 → 3x1 单位四元数向量。"""
    w4 = 2 * np.sqrt(1 + np.trace(R[:3, :3]))
    return np.array([
        (R[2, 1] - R[1, 2]) / w4,
        (R[0, 2] - R[2, 0]) / w4,
        (R[1, 0] - R[0, 1]) / w4,
    ])


def transl(t: np.ndarray) -> np.ndarray:
    """3x1 平移向量 → 4x4 齐次平移矩阵。"""
    T = np.eye(4)
    T[:3, 3] = t
    return T


def rotmat_to_rpy(R: np.ndarray) -> np.ndarray:
    """3x3 旋转矩阵 → RPY (roll, pitch, yaw)。"""
    sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    if sy < 1e-6:
        x = np.arctan2(-R[1, 2], R[1, 1])
        y = np.arctan2(-R[2, 0], sy)
        z = 0.0
    else:
        x = np.arctan2(R[2, 1], R[2, 2])
        y = np.arctan2(-R[2, 0], sy)
        z = np.arctan2(R[1, 0], R[0, 0])
    return np.array([x, y, z])


def rpy_to_rotmat(rpy: np.ndarray) -> np.ndarray:
    """RPY (rad) → 3x3 旋转矩阵。"""
    cr, sr = np.cos(rpy[0]), np.sin(rpy[0])
    cp, sp = np.cos(rpy[1]), np.sin(rpy[1])
    cy, sy = np.cos(rpy[2]), np.sin(rpy[2])
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def pose_to_homogeneous(xyz: np.ndarray, rpy_deg: np.ndarray) -> np.ndarray:
    """位置 (m) + RPY (度) → 4x4 齐次变换矩阵。"""
    R = rpy_to_rotmat(np.deg2rad(rpy_deg))
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = xyz
    return T


def tsai_hand_eye(bHg: list, cHw: list) -> np.ndarray:
    """
    Tsai AX=XB 手眼标定 (全组合模式 K = M*(M-1)/2)。

    移植自 xjbd handEye().

    Args:
        bHg: base→gripper (手臂末端位姿序列), 各为 4x4 齐次矩阵
        cHw: camera→world (棋盘格位姿序列), 各为 4x4 齐次矩阵

    Returns:
        gHc: gripper→camera 4x4 齐次矩阵

    对于 T1 固定相机场景:
        bHg = base→target_link (手臂末端)
        cHw = camera→chessboard (solvePnP 结果)
        返回 X = target_link→chessboard
    """
    M = len(bHg)
    K = (M * M - M) // 2

    Hg = [T.copy() for T in bHg]
    Hc = [T.copy() for T in cHw]

    # ---- Step 1: 求解旋转 ----
    A = np.zeros((3 * K, 3))
    B = np.zeros((3 * K, 1))
    k = 0

    for i in range(M):
        for j in range(i + 1, M):
            # 手臂从 i→j 的运动
            Hgij = np.linalg.solve(Hg[j], Hg[i])       # inv(Hg_j) * Hg_i
            Pgij = 2 * rot2quat(Hgij)

            # 相机从 i→j 的观测
            Hcij = Hc[j] @ np.linalg.inv(Hc[i])         # Hc_j * inv(Hc_i)
            Pcij = 2 * rot2quat(Hcij)

            A[3*k:3*k+3, :] = skew(Pgij + Pcij)
            B[3*k:3*k+3, 0] = Pcij - Pgij
            k += 1

    # 求解 A * Pcg_ = B
    Pcg_, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
    Pcg_ = Pcg_.flatten()

    # 归一化四元数
    Pcg = 2 * Pcg_ / np.sqrt(1 + Pcg_ @ Pcg_)
    Rcg = quat2rot(Pcg / 2)

    # ---- Step 2: 求解平移 ----
    k = 0
    for i in range(M):
        for j in range(i + 1, M):
            Hgij = np.linalg.solve(Hg[j], Hg[i])
            Hcij = Hc[j] @ np.linalg.inv(Hc[i])

            A[3*k:3*k+3, :] = Hgij[:3, :3] - np.eye(3)
            B[3*k:3*k+3, 0] = Rcg @ Hcij[:3, 3] - Hgij[:3, 3]
            k += 1

    Tcg, _, _, _ = np.linalg.lstsq(A[:3*k], B[:3*k], rcond=None)
    Tcg = Tcg.flatten()

    # ---- 组合结果 ----
    gHc = transl(Tcg)
    gHc[:3, :3] = Rcg
    return gHc


# ===================================================================
# SDK 内参 / 外参获取
# ===================================================================

def get_camera_params(serial: str) -> dict:
    """从 SDK 获取 color/depth 内参和外参。"""
    from pyorbbecsdk import Context, OBSensorType, Pipeline, OBLogLevel

    ctx = Context()
    ctx.set_logger_level(OBLogLevel.ERROR)
    device_list = ctx.query_devices()

    device = None
    for i in range(device_list.get_count()):
        d = device_list.get_device_by_index(i)
        if d.get_device_info().get_serial_number() == serial:
            device = d
            break
    if device is None and device_list.get_count() > 0:
        device = device_list.get_device_by_index(0)
        print(f"未找到 serial={serial}，使用: {device.get_device_info().get_serial_number()}")
    if device is None:
        raise RuntimeError("未发现奥比中光相机")

    pipeline = Pipeline(device)

    def _get_intrinsics(profiles, sensor_type):
        p = profiles.get_default_video_stream_profile()
        intr = p.get_intrinsic()
        dist = p.get_distortion() if hasattr(p, "get_distortion") else None
        dlist = _distortion_to_list(dist)
        return {
            "fx": intr.fx, "fy": intr.fy, "cx": intr.cx, "cy": intr.cy,
            "width": p.get_width(), "height": p.get_height(),
            "distortion": dlist,
        }

    color = _get_intrinsics(
        pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR), OBSensorType.COLOR_SENSOR)
    depth = _get_intrinsics(
        pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR), OBSensorType.DEPTH_SENSOR)

    try:
        cp = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR).get_default_video_stream_profile()
        dp = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR).get_default_video_stream_profile()
        extrin = cp.get_extrinsic_to(dp)
        c2d = _extrinsic_to_dict(extrin)
    except Exception:
        print("警告: 无法获取 color→depth 外参")
        c2d = {"rotation": [0, 0, 0], "translation": [0, 0, 0]}

    return {"color_intrinsics": color, "depth_intrinsics": depth, "color_to_depth": c2d}


def _distortion_to_list(dist) -> list:
    if dist is None:
        return [0.0, 0.0, 0.0, 0.0, 0.0]
    try:
        return [dist.k1, dist.k2, dist.p1, dist.p2, dist.k3]
    except AttributeError:
        return [getattr(dist, "k1", 0.0), getattr(dist, "k2", 0.0),
                getattr(dist, "p1", 0.0), getattr(dist, "p2", 0.0),
                getattr(dist, "k3", 0.0)]


def _extrinsic_to_dict(extrin) -> dict:
    rot = extrin.rot
    trans = extrin.transform[:3, 3] if hasattr(extrin, "transform") else np.zeros(3)
    rpy = rotmat_to_rpy(rot)
    return {
        "rotation": [float(rpy[0]), float(rpy[1]), float(rpy[2])],
        "translation": [float(trans[0]), float(trans[1]), float(trans[2])],
    }


# ===================================================================
# 采集 + 标定
# ===================================================================

def _frame_to_bgr(frame) -> Optional[np.ndarray]:
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


def _collect_frames(pipeline, chessboard_size, square_size, num_frames):
    """采集棋盘格图像，返回 (obj_points_list, img_points_list)。"""
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    objp = np.zeros((chessboard_size[0] * chessboard_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:chessboard_size[0], 0:chessboard_size[1]].T.reshape(-1, 2)
    objp *= square_size

    obj_points, img_points = [], []

    print(f"\n采集棋盘格 (需要 {num_frames} 帧, 按 's' 保存, 'q' 退出)")
    print(f"棋盘格: {chessboard_size[0]}x{chessboard_size[1]}, 方格: {square_size}m")

    cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Calibration", 1280, 720)

    captured = 0
    while captured < num_frames:
        frames = pipeline.wait_for_frames(1000)
        if frames is None:
            continue
        cf = frames.get_color_frame()
        if cf is None:
            continue
        img = _frame_to_bgr(cf)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, chessboard_size, None)
        display = img.copy()
        if ret:
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            cv2.drawChessboardCorners(display, chessboard_size, corners2, ret)
            status = f"检测成功 — 按 's' 保存 ({captured + 1}/{num_frames})"
        else:
            status = f"未检测到 — 调整位置 ({captured + 1}/{num_frames})"
        cv2.putText(display, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 255, 0) if ret else (0, 0, 255), 2)
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


def load_poses(pose_file: str, num_required: int) -> list:
    """
    从 pose.txt 读取手臂末端位姿。

    格式: 每行 x y z roll pitch yaw (空格分隔, xyz=m, rpy=deg)
    返回: [4x4_homogeneous_matrix, ...] (base→target_link)
    """
    poses = []
    with open(pose_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 6:
                continue
            xyz = np.array([float(parts[0]), float(parts[1]), float(parts[2])])
            rpy = np.array([float(parts[3]), float(parts[4]), float(parts[5])])
            poses.append(pose_to_homogeneous(xyz, rpy))

    if len(poses) < num_required:
        raise RuntimeError(
            f"pose.txt 中只有 {len(poses)} 个姿态，需要 ≥{num_required} 个"
        )
    print(f"从 {pose_file} 读取了 {len(poses)} 个手臂姿态")
    return poses


def calibrate_tsai(
    obj_points_list: list,
    img_points_list: list,
    K: np.ndarray,
    dist: np.ndarray,
    arm_poses: list,
    target_link: str,
) -> dict:
    """
    Tsai 手眼标定: 计算 camera→target_link。

    流程:
      1. 对每帧 solvePnP → camera→chessboard (cHw)
      2. 用 arm_poses 作为 bHg (base→target_link)
      3. Tsai AX=XB 求解 X = target_link→chessboard
      4. camera→target_link = camera→chessboard_0 * inv(X)
    """
    N = len(obj_points_list)
    print(f"\n运行 solvePnP ({N} 帧)...")

    cHw_list = []  # camera→chessboard
    rvecs, tvecs = [], []
    for i in range(N):
        ret, rvec, tvec = cv2.solvePnP(
            obj_points_list[i], img_points_list[i], K, dist,
        )
        if not ret:
            print(f"  帧 {i}: solvePnP 失败，跳过")
            continue
        rvecs.append(rvec)
        tvecs.append(tvec)
        R, _ = cv2.Rodrigues(rvec)
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = tvec.flatten()
        cHw_list.append(T)

    if len(cHw_list) < 3:
        raise RuntimeError(f"solvePnP 成功帧数不足 ({len(cHw_list)} < 3)")

    # 对齐 arm_poses 和 cHw_list
    bHg = arm_poses[:len(cHw_list)]
    print(f"有效帧数: {len(cHw_list)}")

    # ---- Tsai AX=XB ----
    print("\n运行 Tsai AX=XB 手眼标定...")
    X = tsai_hand_eye(bHg, cHw_list)
    # X = target_link→chessboard

    # 提取旋转轴/角
    R_x = X[:3, :3]
    angle = np.arccos((np.trace(R_x) - 1) / 2)
    axis = np.array([R_x[2, 1] - R_x[1, 2],
                     R_x[0, 2] - R_x[2, 0],
                     R_x[1, 0] - R_x[0, 1]])
    if np.linalg.norm(axis) > 1e-10:
        axis = axis / np.linalg.norm(axis)
    print(f"  target_link→chessboard 旋转轴: {axis}, 角度: {np.rad2deg(angle):.2f}°")

    # camera→target_link = camera→chessboard_0 * inv(X)
    T_cam_tgt = cHw_list[0] @ np.linalg.inv(X)
    rpy = rotmat_to_rpy(T_cam_tgt[:3, :3])

    result = {
        "rotation": [float(rpy[0]), float(rpy[1]), float(rpy[2])],
        "translation": [float(T_cam_tgt[0, 3]), float(T_cam_tgt[1, 3]), float(T_cam_tgt[2, 3])],
    }

    print(f"\n相机 → {target_link} 变换:")
    print(f"  rotation (rpy): [{result['rotation'][0]:.4f}, "
          f"{result['rotation'][1]:.4f}, {result['rotation'][2]:.4f}] rad")
    print(f"  translation (m): [{result['translation'][0]:.4f}, "
          f"{result['translation'][1]:.4f}, {result['translation'][2]:.4f}]")

    # 残差评估
    print("\n标定残差评估 (camera→chessboard 投影):")
    for i in range(len(cHw_list)):
        T_pred = T_cam_tgt @ X @ np.linalg.inv(bHg[i])  # 预测的 camera→chessboard
        # 简化: 只比较平移
        err_t = np.linalg.norm(T_pred[:3, 3] - cHw_list[i][:3, 3])
        print(f"  帧 {i}: 平移残差 = {err_t:.4f} m")

    return result


# ===================================================================
# 写入配置
# ===================================================================

def write_calibration_to_config(camera_id, sdk_params, hand_eye, target_link, config_path):
    path = Path(config_path)
    data = yaml.safe_load(open(path)) if path.exists() else {}
    cameras = data.setdefault("cameras", [])
    target = next((c for c in cameras if c.get("id") == camera_id), None)
    if target is None:
        target = {"id": camera_id}
        cameras.append(target)

    target["calibration"] = {
        "color_intrinsics": sdk_params["color_intrinsics"],
        "depth_intrinsics": sdk_params["depth_intrinsics"],
        "color_to_depth": sdk_params["color_to_depth"],
        f"camera_to_{target_link}": hand_eye,
    }
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"\n标定结果已写入: {path}")


# ===================================================================
# main
# ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Tsai AX=XB 手眼标定 (移植自 xjbd)")
    parser.add_argument("--camera", default="head")
    parser.add_argument("--serial", default="")
    parser.add_argument("--chessboard", default="9x6")
    parser.add_argument("--square", type=float, default=0.025)
    parser.add_argument("--target-link", default="ARM-R-J7_Link")
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--pose-file", default="", help="手臂姿态文件 (pose.txt)")
    parser.add_argument("--config", default=str(_DEFAULT_CONFIG))
    args = parser.parse_args()

    w, h = map(int, args.chessboard.split("x"))
    chessboard_size = (w, h)

    # 获取 serial
    serial = args.serial
    if not serial:
        try:
            data = yaml.safe_load(open(args.config)) or {}
            for c in data.get("cameras", []):
                if c.get("id") == args.camera:
                    serial = c.get("serial", "")
                    break
        except FileNotFoundError:
            pass
    if not serial:
        print("未指定 serial，使用第一个已连接相机")

    # 1. SDK 内参/外参
    print("=" * 60)
    print("步骤 1: SDK 内参/外参")
    print("=" * 60)
    sdk_params = get_camera_params(serial)
    c = sdk_params["color_intrinsics"]
    print(f"  Color: {c['width']}x{c['height']} fx={c['fx']:.1f} fy={c['fy']:.1f}")
    d = sdk_params["depth_intrinsics"]
    print(f"  Depth: {d['width']}x{d['height']} fx={d['fx']:.1f} fy={d['fy']:.1f}")

    K = np.array([[c["fx"], 0, c["cx"]], [0, c["fy"], c["cy"]], [0, 0, 1]], dtype=np.float64)
    dist = np.array(c["distortion"][:5], dtype=np.float64)

    # 2. 启动 Pipeline
    from pyorbbecsdk import Config, Context, OBLogLevel, OBSensorType, Pipeline
    ctx = Context()
    ctx.set_logger_level(OBLogLevel.ERROR)
    dl = ctx.query_devices()
    device = next((dl.get_device_by_index(i) for i in range(dl.get_count())
                   if dl.get_device_by_index(i).get_device_info().get_serial_number() == serial), None)
    if device is None and dl.get_count() > 0:
        device = dl.get_device_by_index(0)
    if device is None:
        raise RuntimeError("未发现相机")

    pipeline = Pipeline(device)
    cfg = Config()
    cfg.enable_stream(
        pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
        .get_default_video_stream_profile())
    pipeline.start(cfg)
    print("Pipeline 已启动")

    try:
        # 3. 采集棋盘格
        print(f"\n{'=' * 60}")
        print(f"步骤 2: 采集棋盘格")
        print(f"{'=' * 60}")
        obj_pts, img_pts = _collect_frames(pipeline, chessboard_size, args.square, args.frames)

        # 4. 加载手臂姿态
        print(f"\n{'=' * 60}")
        print(f"步骤 3: Tsai 手眼标定")
        print(f"{'=' * 60}")

        if args.pose_file:
            arm_poses = load_poses(args.pose_file, len(obj_pts))
        else:
            print("\n未指定 --pose-file，请输入每帧对应的手臂末端位姿:")
            print("格式: x y z roll pitch yaw (米, 度)")
            arm_poses = []
            for i in range(len(obj_pts)):
                print(f"\n帧 {i + 1}/{len(obj_pts)}:")
                line = input("  位姿: ").strip()
                parts = line.split()
                if len(parts) < 6:
                    print("  格式错误，跳过此帧")
                    continue
                xyz = np.array([float(p) for p in parts[:3]])
                rpy = np.array([float(p) for p in parts[3:6]])
                arm_poses.append(pose_to_homogeneous(xyz, rpy))

        hand_eye = calibrate_tsai(
            obj_pts, img_pts, K, dist, arm_poses, args.target_link)

        # 5. 写入配置
        print(f"\n{'=' * 60}")
        print(f"步骤 4: 写入 camera_config.yaml")
        print(f"{'=' * 60}")
        write_calibration_to_config(
            args.camera, sdk_params, hand_eye, args.target_link, args.config)

        print("\n标定完成!")
    finally:
        pipeline.stop()


if __name__ == "__main__":
    main()

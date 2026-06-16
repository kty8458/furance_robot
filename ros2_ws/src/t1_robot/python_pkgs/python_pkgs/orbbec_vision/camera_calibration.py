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
  - 移动手臂到不同姿态，每帧自动记录:
    (a) arm 末端位姿 base→target_link (从 TF2 /tf 实时获取)
    (b) 相机→棋盘格 (solvePnP)

Tsai 方程:
  令 A_ij = inv(base→target_link_i) * base→target_link_j    (TF 获取)
  令 B_ij = camera→chessboard_j * inv(camera→chessboard_i)   (solvePnP)
  求解 AX=XB 得到 X = target_link→chessboard                 (未知常量)
  则 camera→target_link = camera→chessboard_i * inv(X)

用法:
  python3 camera_calibration.py \\
    --camera head \\
    --chessboard 11x8 \\
    --square 0.02 \\
    --target-link ARM-R-J7_Link
"""

import argparse
import os
import sys
import time
from datetime import datetime
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


def get_tf_pose(buffer, target_link: str, base_link: str = "base_link") -> Optional[np.ndarray]:
    """
    从 TF2 Buffer 获取 base_link → target_link 的 4x4 齐次变换矩阵。

    Returns None if transform is unavailable.
    """
    import rclpy
    from geometry_msgs.msg import TransformStamped
    try:
        t: TransformStamped = buffer.lookup_transform(base_link, target_link, rclpy.time.Time())
        trans = t.transform.translation
        rot = t.transform.rotation
        x, y, z, w = rot.x, rot.y, rot.z, rot.w
        R = np.array([
            [1 - 2*y*y - 2*z*z, 2*x*y - 2*w*z,     2*x*z + 2*w*y],
            [2*x*y + 2*w*z,     1 - 2*x*x - 2*z*z, 2*y*z - 2*w*x],
            [2*x*z - 2*w*y,     2*y*z + 2*w*x,     1 - 2*x*x - 2*y*y],
        ])
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = [trans.x, trans.y, trans.z]
        return T
    except Exception:
        return None


def _collect_frames_with_tf(pipeline, chessboard_size, square_size, num_frames,
                            target_link: str, base_link: str = "base_link",
                            camera_id: str = "head"):
    """
    采集棋盘格图像 + 同步 TF 位姿 + 关节角。

    每次按 's' 保存时:
      - data/<camera_id>/<timestamp>/frame_NNNN_raw.png       — 原始图像
      - data/<camera_id>/<timestamp>/frame_NNNN_annotated.png — 带棋盘格标注的图像
      - data/<camera_id>/<timestamp>/records.txt              — 每条记录追加 TF + 关节角

    Returns: (obj_points_list, img_points_list, arm_poses_list)
    """
    import rclpy
    from tf2_ros import Buffer, TransformListener
    from sensor_msgs.msg import JointState

    rclpy.init()
    node = rclpy.create_node("calib_tf_listener")
    tf_buffer = Buffer()
    TransformListener(tf_buffer, node)

    # ---- 创建 session 目录: data/<camera_id>/<timestamp>/ ----
    _MODULE_DIR = Path(__file__).resolve().parent
    session_dir = _MODULE_DIR / "data" / camera_id / datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir.mkdir(parents=True, exist_ok=True)
    records_path = session_dir / "records.txt"
    print(f"\n数据保存目录: {session_dir}")

    # ---- 关节角缓存 (从 /joint_states 订阅) ----
    _joint_state: dict = {}

    def _joint_cb(msg: JointState):
        for i, name in enumerate(msg.name):
            if i < len(msg.position):
                _joint_state[name] = float(msg.position[i])

    joint_sub = node.create_subscription(JointState, "/joint_states", _joint_cb, 10)
    # 等待第一条 joint_states 到达
    for _ in range(50):
        rclpy.spin_once(node, timeout_sec=0.1)
        if _joint_state:
            break
    if _joint_state:
        print(f"已订阅 /joint_states ({len(_joint_state)} 个关节)")
    else:
        print("警告: 未收到 /joint_states (关节角将为空)")

    # ---- 初始化 records.txt 头部 ----
    with open(records_path, "w") as f:
        f.write(f"# 手眼标定采集记录\n")
        f.write(f"# 相机: {camera_id}\n")
        f.write(f"# 日期: {datetime.now().isoformat()}\n")
        f.write(f"# 棋盘格: {chessboard_size[0]}x{chessboard_size[1]}, 方格: {square_size}m\n")
        f.write(f"# TF: {base_link} → {target_link}\n")
        f.write(f"# 格式: frame_index | timestamp | "
                f"tf_tx tf_ty tf_tz tf_qx tf_qy tf_qz tf_qw | "
                f"joint_name1=pos1 joint_name2=pos2 ...\n")
        f.write(f"{'=' * 80}\n")

    # ---- 采集循环 ----
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    objp = np.zeros((chessboard_size[0] * chessboard_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:chessboard_size[0], 0:chessboard_size[1]].T.reshape(-1, 2)
    objp *= square_size

    obj_points, img_points, arm_poses = [], [], []

    print(f"\n采集棋盘格 (需要 {num_frames} 帧, 按 's' 保存, 'q' 退出)")
    print(f"棋盘格: {chessboard_size[0]}x{chessboard_size[1]}, 方格: {square_size}m")
    print(f"TF 链路: {base_link} → {target_link}")
    print("保存时自动记录 TF 位姿 + 关节角 + 图像")

    cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Calibration", 1280, 720)

    _debug_printed = False
    captured = 0
    while captured < num_frames:
        frames = pipeline.wait_for_frames(100)
        if frames is None:
            rclpy.spin_once(node, timeout_sec=0.01)
            continue
        cf = frames.get_color_frame()
        if cf is None:
            rclpy.spin_once(node, timeout_sec=0.01)
            continue
        img = _frame_to_bgr(cf)
        if img is None:
            rclpy.spin_once(node, timeout_sec=0.01)
            continue

        if not _debug_printed:
            _debug_printed = True
            print(f"[DEBUG] 帧格式: {cf.get_format()}, 分辨率: {cf.get_width()}x{cf.get_height()}")
            print(f"[DEBUG] BGR 图像 shape: {img.shape}, dtype: {img.dtype}")
            print(f"[DEBUG] 棋盘格: {chessboard_size[0]}x{chessboard_size[1]}, 方格: {square_size}m")
            debug_path = _MODULE_DIR / "_debug_first_frame.png"
            cv2.imwrite(str(debug_path), img)
            print(f"[DEBUG] 首帧已保存: {debug_path}")
            gray_tmp = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            print(f"[DEBUG] 灰度: min={gray_tmp.min()} max={gray_tmp.max()} "
                  f"mean={gray_tmp.mean():.1f} std={gray_tmp.std():.1f}")
            print(f"[DEBUG] 尝试检测多种棋盘格尺寸...")
            for try_w, try_h in [(12, 9), (11, 8), (10, 7), (9, 6), (8, 6), (8, 5), (7, 5), (6, 4)]:
                r_try, _ = cv2.findChessboardCornersSB(
                    gray_tmp, (try_w, try_h),
                    cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_NORMALIZE_IMAGE)
                if r_try:
                    print(f"  ✓ 检测成功: {try_w}x{try_h} — 请用 --chessboard {try_w}x{try_h}")
                else:
                    r_try2, _ = cv2.findChessboardCorners(
                        gray_tmp, (try_w, try_h),
                        cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)
                    if r_try2:
                        print(f"  ✓ 检测成功(传统): {try_w}x{try_h} — 请用 --chessboard {try_w}x{try_h}")
            print(f"[DEBUG] 尺寸探测完成，以上 ✓ 的尺寸才能正常检测")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        sb_flags = cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_NORMALIZE_IMAGE
        ret, corners = cv2.findChessboardCornersSB(gray, chessboard_size, sb_flags)
        if not ret:
            fallback_flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
            ret, corners = cv2.findChessboardCorners(gray, chessboard_size, fallback_flags)

        # 构建标注图
        display = img.copy()
        if ret:
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            cv2.drawChessboardCorners(display, chessboard_size, corners2, ret)
        else:
            corners2 = corners

        rclpy.spin_once(node, timeout_sec=0.01)
        tf_pose = get_tf_pose(tf_buffer, target_link, base_link)
        tf_str = "TF:OK" if tf_pose is not None else "TF:--"

        if ret:
            status = f"OK — s=save ({captured + 1}/{num_frames}) {tf_str}"
        else:
            status = f"no board ({captured + 1}/{num_frames}) {tf_str}"
        cv2.putText(display, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 255, 0) if ret else (0, 0, 255), 2)
        cv2.imshow("Calibration", display)

        key = cv2.waitKey(1)
        if key == ord("q"):
            break
        elif key == ord("s") and ret and tf_pose is not None:
            # ---- 保存图像和数据 ----
            idx_str = f"{captured + 1:04d}"
            raw_path = session_dir / f"frame_{idx_str}_raw.png"
            anno_path = session_dir / f"frame_{idx_str}_annotated.png"
            cv2.imwrite(str(raw_path), img)
            cv2.imwrite(str(anno_path), display)

            # TF 四元数
            import rclpy as _rclpy
            from geometry_msgs.msg import TransformStamped as _TS
            t_stamped: _TS = tf_buffer.lookup_transform(base_link, target_link, _rclpy.time.Time())
            t_t = t_stamped.transform.translation
            t_r = t_stamped.transform.rotation

            # 写入 records.txt
            ts = datetime.now().isoformat()
            tf_line = (f"{t_t.x:.6f} {t_t.y:.6f} {t_t.z:.6f} "
                       f"{t_r.x:.6f} {t_r.y:.6f} {t_r.z:.6f} {t_r.w:.6f}")
            joint_line = " ".join(f"{k}={v:.6f}" for k, v in sorted(_joint_state.items()))
            with open(records_path, "a") as f:
                f.write(f"{idx_str} | {ts} | {tf_line} | {joint_line}\n")

            obj_points.append(objp)
            img_points.append(corners2)
            arm_poses.append(tf_pose)
            captured += 1
            print(f"  [{captured}/{num_frames}] "
                  f"t=[{tf_pose[0,3]:.3f},{tf_pose[1,3]:.3f},{tf_pose[2,3]:.3f}] "
                  f"→ {raw_path.name}, {anno_path.name}")
        elif key == ord("s") and ret and tf_pose is None:
            print(f"  skip: TF unavailable ({base_link}->{target_link})")

        time.sleep(0.03)

    cv2.destroyAllWindows()
    node.destroy_node()
    rclpy.shutdown()
    print(f"采集完成: {captured} 帧")
    print(f"数据保存在: {session_dir}\n")
    return obj_points, img_points, arm_poses


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
    parser.add_argument("--chessboard", default="11x8")
    parser.add_argument("--square", type=float, default=0.02)
    parser.add_argument("--target-link", default="ARM-R-J7_Link")
    parser.add_argument("--frames", type=int, default=20)
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
        # 3. 采集棋盘格 + TF 位姿
        print(f"\n{'=' * 60}")
        print(f"步骤 2: 采集棋盘格 + TF 位姿")
        print(f"{'=' * 60}")
        obj_pts, img_pts, arm_poses = _collect_frames_with_tf(
            pipeline, chessboard_size, args.square, args.frames,
            args.target_link, camera_id=args.camera,
        )

        # 4. Tsai 手眼标定
        print(f"\n{'=' * 60}")
        print(f"步骤 3: Tsai 手眼标定")
        print(f"{'=' * 60}")

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

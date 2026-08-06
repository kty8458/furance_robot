#!/usr/bin/env python3
"""
标定精度验证脚本 - 检查相机外参标定质量。

原理: 棋盘格固定在世界中, 不同头部姿态下相机观测棋盘格位置不同。
      用标定出的 camera->target_link 外参, 把每帧的 camera->chessboard
      转到 base_link 坐标系, 检查 base->chessboard 是否一致 (应该不变)。

用法:
  # 用最新采集的标定数据验证 (自动找 data/head/ 下最新目录)
  python3 verify_calibration.py --camera head --target-link tou2_Link --mode eye-in-hand

  # 指定数据目录
  python3 verify_calibration.py --camera head --target-link tou2_Link --mode eye-in-hand \
    --data-dir data/head/20260806_092833

  # 指定棋盘格参数
  python3 verify_calibration.py --camera head --target-link tou2_Link --mode eye-in-hand \
    --chessboard 11x8 --square 0.02

依赖: pyorbbecsdk (读相机内参), opencv (solvePnP)
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np
import yaml

_here = Path(__file__).resolve().parent
_DEFAULT_CONFIG = _here / "camera_config.yaml"

# Tsai 算法 (复用 camera_calibration.py)
sys.path.insert(0, str(_here))
from camera_calibration import (
    rotmat_to_rpy, quat2rot, rot2quat, skew, transl,
    tsai_hand_eye, _find_device, _get_camera_params_from_device,
    _frame_to_bgr,
)


def load_intrinsics(camera_id, config_path):
    """从 camera_config.yaml 读内参。"""
    data = yaml.safe_load(open(config_path)) or {}
    for c in data.get("cameras", []):
        if c.get("id") == camera_id:
            calib = c.get("calibration", {})
            ci = calib.get("color_intrinsics", {})
            if ci.get("fx"):
                K = np.array([[ci["fx"], 0, ci["cx"]], [0, ci["fy"], ci["cy"]], [0, 0, 1]])
                dist = np.array(ci.get("distortion", [0, 0, 0, 0, 0]))
                return K, dist
    return None, None


def load_hand_eye(camera_id, target_link, config_path):
    """从 camera_config.yaml 读 camera->target_link 外参。"""
    data = yaml.safe_load(open(config_path)) or {}
    for c in data.get("cameras", []):
        if c.get("id") == camera_id:
            calib = c.get("calibration", {})
            he = calib.get(f"camera_to_{target_link}")
            if he:
                rpy = he.get("rotation", [0, 0, 0])
                t = he.get("translation", [0, 0, 0])
                # RPY -> 旋转矩阵
                rx, ry, rz = rpy
                Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)], [0, np.sin(rx), np.cos(rx)]])
                Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0], [-np.sin(ry), 0, np.cos(ry)]])
                Rz = np.array([[np.cos(rz), -np.sin(rz), 0], [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
                R = Rz @ Ry @ Rx
                T = np.eye(4)
                T[:3, :3] = R
                T[:3, 3] = [float(x) for x in t]
                return T
    return None


def load_records(data_dir):
    """从 records.txt 读 TF 位姿。"""
    records = []
    path = Path(data_dir) / "records.txt"
    if not path.exists():
        print(f"错误: {path} 不存在")
        return records
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("="):
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            idx = parts[0].strip()
            tf_vals = parts[2].strip().split()
            if len(tf_vals) < 7:
                continue
            tx, ty, tz = float(tf_vals[0]), float(tf_vals[1]), float(tf_vals[2])
            qx, qy, qz, qw = float(tf_vals[3]), float(tf_vals[4]), float(tf_vals[5]), float(tf_vals[6])
            R = np.array([
                [1-2*qy*qy-2*qz*qz, 2*qx*qy-2*qz*qw, 2*qx*qz+2*qy*qw],
                [2*qx*qy+2*qz*qw, 1-2*qx*qx-2*qz*qz, 2*qy*qz-2*qx*qw],
                [2*qx*qz-2*qy*qw, 2*qy*qz+2*qx*qw, 1-2*qx*qx-2*qy*qy],
            ])
            T = np.eye(4)
            T[:3, :3] = R
            T[:3, 3] = [tx, ty, tz]
            records.append({"idx": idx, "T_base_target": T})
    return records


def load_images_and_chessboard(data_dir, chessboard_size, square_size, K, dist):
    """从数据目录读图像, 检测棋盘格, solvePnP 得 camera->chessboard。"""
    data_dir = Path(data_dir)
    cHw_list = []
    valid_indices = []
    w, h = chessboard_size
    objp = np.zeros((w * h, 3), np.float32)
    objp[:, :2] = np.mgrid[0:w, 0:h].T.reshape(-1, 2)
    objp *= square_size

    for img_path in sorted(data_dir.glob("frame_*_raw.png")):
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCornersSB(gray, chessboard_size,
            cv2.CALIB_CB_EXHAUSTIVE + cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not ret:
            ret, corners = cv2.findChessboardCorners(gray, chessboard_size,
                cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE)
        if not ret:
            print(f"  {img_path.name}: 棋盘格未检测到, 跳过")
            continue
        corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
        ok, rvec, tvec = cv2.solvePnP(objp, corners2, K, dist)
        if not ok:
            continue
        R, _ = cv2.Rodrigues(rvec)
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = tvec.flatten()
        cHw_list.append(T)
        idx = img_path.stem.split("_")[1]
        valid_indices.append(idx)
        print(f"  {img_path.name}: solvePnP OK, t=[{T[0,3]:.3f},{T[1,3]:.3f},{T[2,3]:.3f}]")

    return cHw_list, valid_indices


def verify(data_dir, K, dist, T_cam_target, records, mode):
    """验证: 把每帧 camera->chessboard 转到 base_link, 检查一致性。"""
    cHw_list, valid_indices = load_images_and_chessboard(
        data_dir, args.chessboard, args.square, K, dist)

    if len(cHw_list) < 2:
        print("有效帧数不足, 无法验证")
        return

    # 匹配 records 和图像 (按 idx)
    bHg_list = []
    matched_cHw = []
    for i, idx in enumerate(valid_indices):
        for r in records:
            if r["idx"] == idx:
                bHg_list.append(r["T_base_target"])
                matched_cHw.append(cHw_list[i])
                break

    if len(bHg_list) < 2:
        print(f"匹配的 records 不足 ({len(bHg_list)}), 无法验证")
        return

    print(f"\n{'='*60}")
    print(f"精度验证: {len(bHg_list)} 帧")
    print(f"模式: {mode}")
    print(f"{'='*60}")

    # eye-in-hand: 相机随头部动, 棋盘格固定在世界
    # base->chessboard = base->target * target->camera * camera->chessboard
    #                 = bHg * inv(T_cam_target) * cHw
    # 应为常量, 检查各帧一致性
    if mode == "eye-in-hand":
        print("\n检查 base->chessboard 一致性 (应为常量):")
        base_to_boards = []
        for i in range(len(bHg_list)):
            T_base_board = bHg_list[i] @ np.linalg.inv(T_cam_target) @ matched_cHw[i]
            base_to_boards.append(T_base_board)

        translations = np.array([T[:3, 3] for T in base_to_boards])
        mean_t = translations.mean(axis=0)
        std_t = translations.std(axis=0)

        print(f"  棋盘格在 base_link 系的平均位置: [{mean_t[0]:.4f}, {mean_t[1]:.4f}, {mean_t[2]:.4f}] m")
        print(f"  标准差: [{std_t[0]:.4f}, {std_t[1]:.4f}, {std_t[2]:.4f}] m")
        print(f"  最大偏差: {np.max(np.linalg.norm(translations - mean_t, axis=1)):.4f} m")

        print("\n各帧详情:")
        for i, T in enumerate(base_to_boards):
            err = np.linalg.norm(T[:3, 3] - mean_t)
            print(f"  帧 {valid_indices[i]}: t=[{T[0,3]:.4f},{T[1,3]:.4f},{T[2,3]:.4f}] "
                  f"偏差={err:.4f} m ({err*1000:.1f} mm)")

        # 旋转一致性
        rotations = [T[:3, :3] for T in base_to_boards]
        mean_angle_err = 0
        for i in range(len(rotations)):
            R_diff = rotations[i] @ rotations[0].T
            angle = np.arccos(np.clip((np.trace(R_diff) - 1) / 2, -1, 1))
            mean_angle_err += np.degrees(angle)
        if len(rotations) > 1:
            mean_angle_err /= (len(rotations) - 1)
        print(f"\n  旋转平均偏差: {mean_angle_err:.2f}°")

        # 总结
        max_err_mm = np.max(np.linalg.norm(translations - mean_t, axis=1)) * 1000
        print(f"\n{'='*60}")
        if max_err_mm < 5:
            print(f"✅ 精度良好: 最大平移偏差 {max_err_mm:.1f} mm (< 5mm)")
        elif max_err_mm < 15:
            print(f"⚠️  精度一般: 最大平移偏差 {max_err_mm:.1f} mm (5-15mm)")
        else:
            print(f"❌ 精度较差: 最大平移偏差 {max_err_mm:.1f} mm (> 15mm), 建议重新标定")
        print(f"   旋转平均偏差: {mean_angle_err:.2f}°")
        print(f"{'='*60}")

    else:
        # eye-to-hand: 相机固定, 棋盘格在臂上
        # camera->chessboard 应随臂运动变化, 检查投影残差
        print("\n检查投影残差 (camera->chessboard 投影一致性):")
        for i in range(len(bHg_list)):
            T_pred = T_cam_target @ np.linalg.inv(bHg_list[i])
            err_t = np.linalg.norm(T_pred[:3, 3] - matched_cHw[i][:3, 3])
            print(f"  帧 {valid_indices[i]}: 平移残差 = {err_t:.4f} m ({err_t*1000:.1f} mm)")


def main():
    global args
    parser = argparse.ArgumentParser(description="标定精度验证")
    parser.add_argument("--camera", default="head")
    parser.add_argument("--target-link", default="tou2_Link")
    parser.add_argument("--mode", default="eye-in-hand", choices=["eye-to-hand", "eye-in-hand"])
    parser.add_argument("--chessboard", default="11x8")
    parser.add_argument("--square", type=float, default=0.02)
    parser.add_argument("--config", default=str(_DEFAULT_CONFIG))
    parser.add_argument("--data-dir", default="", help="采集数据目录 (空=自动找最新)")
    args = parser.parse_args()

    w, h = map(int, args.chessboard.split("x"))

    # 1. 读内参
    K, dist = load_intrinsics(args.camera, args.config)
    if K is None:
        # 从 SDK 获取
        print("camera_config.yaml 无内参, 从 SDK 获取...")
        device, info = _find_device(args.camera)
        if device is None:
            sys.exit("无法找到相机设备")
        params = _get_camera_params_from_device(device)
        ci = params["color_intrinsics"]
        K = np.array([[ci["fx"], 0, ci["cx"]], [0, ci["fy"], ci["cy"]], [0, 0, 1]])
        dist = np.array(ci.get("distortion", [0, 0, 0, 0, 0]))
    print(f"内参: fx={K[0,0]:.1f} fy={K[1,1]:.1f} cx={K[0,2]:.1f} cy={K[1,2]:.1f}")

    # 2. 读外参 (标定结果)
    T_cam_target = load_hand_eye(args.camera, args.target_link, args.config)
    if T_cam_target is None:
        sys.exit(f"camera_config.yaml 中无 camera_to_{args.target_link} 标定结果")
    rpy = rotmat_to_rpy(T_cam_target[:3, :3])
    print(f"外参 camera->{args.target_link}: "
          f"t=[{T_cam_target[0,3]:.4f},{T_cam_target[1,3]:.4f},{T_cam_target[2,3]:.4f}] "
          f"rpy=[{np.degrees(rpy[0]):.1f},{np.degrees(rpy[1]):.1f},{np.degrees(rpy[2]):.1f}]°")

    # 3. 找数据目录
    if args.data_dir:
        data_dir = args.data_dir
    else:
        dirs = sorted(Path(_here / "data" / args.camera).glob("*/"))
        if not dirs:
            sys.exit(f"无采集数据 (data/{args.camera}/)")
        data_dir = str(dirs[-1])
    print(f"数据目录: {data_dir}")

    # 4. 读 records
    records = load_records(data_dir)
    if not records:
        sys.exit("无 records.txt 或无有效记录")
    print(f"records: {len(records)} 条")

    # 5. 验证
    verify(data_dir, K, dist, T_cam_target, records, args.mode)


if __name__ == "__main__":
    main()

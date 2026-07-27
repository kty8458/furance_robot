#!/usr/bin/env python3
"""
点云 + YOLO 匹配抓取点检测 - 单帧测试 (相机坐标系, 不接 ROS2/TF)。

流程:
  1. 启动相机 color+depth 流 (硬件 D2C 对齐)
  2. 取一帧: YOLO 分割取杆 mask
  3. mask 区域 + aligned depth + color 内参 -> 点云 (相机光学系)
  4. 统计滤波 + 半径滤波去噪
  5. PCA 拟合杆主轴方向
  6. 沿轴剖分, 算各段直径, 找直径突变点 (粗段中心=抓取点)
  7. 抓取点 + 轴向反投影到 RGB, 画坐标轴 + 抓取点, 输出图片

输出: grasp_test_out.jpg (含坐标轴 + 抓取点 + 杆轴 + 突变位置)
依赖: pyorbbecsdk, ultralytics(系统python3), onnxruntime, open3d, opencv
"""

import argparse
import os
import sys

# ---- pyorbbecsdk 原生库路径修复 (须在 import 前) ----
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

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
from yolo_detector import YOLODetector

import open3d as o3d
import yaml

DEFAULT_MODEL = os.path.join(_here, "models", "train", "weights", "best.onnx")
DEFAULT_NAMES = ["gan 1"]
DEFAULT_CFG = os.path.join(_here, "camera_config.yaml")
DEFAULT_OUT = os.path.join(_here, "grasp_test_out.jpg")

# ---- 算法参数 ----
MIN_DEPTH_M = 0.3
MAX_DEPTH_M = 2.0
STAT_FILTER_NB = 20
STAT_FILTER_STD = 2.0
RADIUS_FILTER_R = 0.02
RADIUS_FILTER_MIN = 5
PROFILE_BINS = 20          # 沿轴剖分段数
DIAMETER_JUMP_RATIO = 1.3  # 粗/细 > 1.3 判为突变


def parse_args():
    p = argparse.ArgumentParser(description="点云+YOLO 抓取点单帧测试 (相机坐标系)")
    p.add_argument("--camera", default="right_arm")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--names", default=",".join(DEFAULT_NAMES))
    p.add_argument("--config", default=DEFAULT_CFG, help="camera_config.yaml 路径")
    p.add_argument("--conf", type=float, default=0.5)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--depth", default=None, help="直接用本地 depth(毫米 uint16) + --color, 跳过相机")
    p.add_argument("--color", default=None, help="本地 color 图 (配合 --depth)")
    return p.parse_args()


def load_intrinsics(config_path, camera_id):
    with open(config_path) as f:
        d = yaml.safe_load(f)
    for c in d["cameras"]:
        if c["id"] == camera_id:
            ci = c["calibration"]["color_intrinsics"]
            di = c["calibration"]["depth_intrinsics"]
            K_color = np.array([[ci["fx"], 0, ci["cx"]], [0, ci["fy"], ci["cy"]], [0, 0, 1]], dtype=np.float64)
            K_depth = np.array([[di["fx"], 0, di["cx"]], [0, di["fy"], di["cy"]], [0, 0, 1]], dtype=np.float64)
            return {"color": K_color, "depth": K_depth}, ci, di
    raise RuntimeError(f"camera {camera_id} not in config")


def grab_one_frame(camera_id, config_path):
    """启动 color+depth 硬件对齐流, 取一帧。返回 (color_bgr, depth_m 单位米)。"""
    import time
    from pyorbbecsdk import Context, Pipeline, Config, OBSensorType

    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cam_cfg = next(c for c in cfg["cameras"] if c["id"] == camera_id)
    target_serial = cam_cfg["serial"]

    ctx = Context()
    dl = ctx.query_devices()
    device = None
    for i in range(dl.get_count()):
        d = dl.get_device_by_index(i)
        if d.get_device_info().get_serial_number() == target_serial:
            device = d
            break
    if device is None:
        raise RuntimeError(f"相机 {camera_id} (serial={target_serial}) 未连接")

    pipe = Pipeline(device)
    config = Config()
    config.enable_stream(pipe.get_stream_profile_list(OBSensorType.COLOR_SENSOR).get_default_video_stream_profile())
    config.enable_stream(pipe.get_stream_profile_list(OBSensorType.DEPTH_SENSOR).get_default_video_stream_profile())
    # depth->color 对齐 + start: HW_MODE 优先, start 失败则回退 SW_MODE
    from pyorbbecsdk import OBAlignMode
    pipe_started = False
    for mode, label in [(OBAlignMode.HW_MODE, "硬件 D2C"), (OBAlignMode.SW_MODE, "软件 D2C")]:
        try:
            config.set_align_mode(mode)
            pipe.start(config)
            print(f"[相机] 对齐: {label}, pipeline started")
            pipe_started = True
            break
        except Exception as e:
            print(f"[相机] {label} 失败: {e}")
            try:
                pipe.stop()
            except Exception:
                pass
    if not pipe_started:
        # 都失败: 不对齐直接 start (depth/color 尺寸不一致, mask_to_pointcloud 会 resize mask)
        try:
            config.set_align_mode(OBAlignMode.DISABLE)
            pipe.start(config)
            print("[相机] 对齐不可用, 直接启动 (depth/color 尺寸不一致, 将手动 resize mask)")
        except Exception as e:
            raise RuntimeError(f"pipeline 启动失败: {e}")
    time.sleep(1.0)

    color_bgr = None
    depth_mm = None
    for _ in range(30):
        fs = pipe.wait_for_frames(1000)
        if fs is None:
            continue
        cf = fs.get_color_frame()
        df = fs.get_depth_frame()
        if cf is not None and df is not None:
            color_bgr = _frame_to_bgr(cf)
            depth_mm = _frame_to_depth_mm(df)
            if color_bgr is not None and depth_mm is not None:
                break
        time.sleep(0.03)
    pipe.stop()
    if color_bgr is None or depth_mm is None:
        raise RuntimeError("取帧失败")
    print(f"[相机] 取帧成功: color {color_bgr.shape}, depth {depth_mm.shape}")
    return color_bgr, depth_mm


def _frame_to_bgr(frame):
    from pyorbbecsdk import OBFormat
    w, h, fmt = frame.get_width(), frame.get_height(), frame.get_format()
    data = np.asanyarray(frame.get_data())
    if fmt == OBFormat.RGB:
        return cv2.cvtColor(data.reshape((h, w, 3)), cv2.COLOR_RGB2BGR)
    elif fmt == OBFormat.BGR:
        return data.reshape((h, w, 3))
    elif fmt == OBFormat.MJPG:
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    return None


def _frame_to_depth_mm(frame):
    """depth frame -> 米 (float32)。pyorbbecsdk raw 是 uint16 毫米值。"""
    w, h = frame.get_width(), frame.get_height()
    raw = np.frombuffer(frame.get_data(), dtype=np.uint16)
    return (raw.reshape((h, w)).astype(np.float32)) / 1000.0  # mm -> m


# ============ 点云 + 抓取点算法 ============

def mask_to_pointcloud(color_bgr, depth_m, mask, K_depth):
    """mask 区域 -> 相机光学系点云 (open3d)。

    用 depth 原始尺寸 + depth 内参 (depth 未与 color 对齐时)。
    mask resize 到 depth 尺寸。color 仅用于点云着色 (resize 到 depth)。
    depth_m 单位: 米。
    """
    h, w = depth_m.shape
    # mask resize 到 depth 尺寸
    if mask.shape != depth_m.shape:
        mask_r = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
    else:
        mask_r = mask
    valid = (depth_m > MIN_DEPTH_M) & (depth_m < MAX_DEPTH_M) & mask_r

    ys, xs = np.where(valid)
    if len(xs) < 50:
        return None, None
    depths = depth_m[ys, xs]
    fx, fy = K_depth[0, 0], K_depth[1, 1]
    cx, cy = K_depth[0, 2], K_depth[1, 2]
    # 光学系: x 右, y 下, z 前
    x = (xs - cx) * depths / fx
    y = (ys - cy) * depths / fy
    z = depths
    pts = np.stack([x, y, z], axis=1).astype(np.float32)
    # color 着色 (resize color 到 depth 尺寸)
    if color_bgr is not None:
        color_r = cv2.resize(color_bgr, (w, h))
        colors = color_r[ys, xs][:, ::-1] / 255.0  # BGR->RGB
    else:
        colors = None

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    if colors is not None:
        pcd.colors = o3d.utility.Vector3dVector(colors.astype(np.float64))
    return pcd, pts


def filter_pointcloud(pcd):
    """统计滤波 + 半径滤波去噪。"""
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=STAT_FILTER_NB, std_ratio=STAT_FILTER_STD)
    if len(pcd.points) < 50:
        return pcd
    pcd, _ = pcd.remove_radius_outlier(nb_points=RADIUS_FILTER_MIN, radius=RADIUS_FILTER_R)
    return pcd


def remove_background(pts, axis, center):
    """剔除框/滑槽等背景点。

    杆点云到轴距离呈"中心密集+表面环"分布, 框/滑槽在杆下方, 距离轴更远。
    策略: 用 90 分位距离作为杆表面半径估计, 保留 <= 1.2×该半径的点
    (剔除框等远处点)。不用直方图峰值 (峰值在中心, 非表面)。
    """
    d = pts - center
    proj = d @ axis
    perp = d - np.outer(proj, axis)
    dists = np.linalg.norm(perp, axis=1)
    # 90 分位 ≈ 杆表面半径 (杆点占多数, 表面环在 75-90 分位)
    surface_r = float(np.percentile(dists, 90))
    keep_r = surface_r * 1.2
    keep = dists <= keep_r
    n_before = len(pts)
    pts = pts[keep]
    print(f"[背景剔除] 表面半径~{surface_r*1000:.1f}mm, 保留<={keep_r*1000:.1f}mm 的点: "
          f"{len(pts)}/{n_before} (剔除框/滑槽远处点)")
    return pts


def fit_axis_pca(pts):
    """PCA 拟合杆主轴。返回 (axis_dir(3,), center(3,), eigenvalues)。"""
    center = pts.mean(axis=0)
    cov = np.cov(pts.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    # 最大特征值方向 = 主轴 (杆最长方向)
    axis = eigvecs[:, -1]
    if axis[2] < 0:  # 让轴朝相机方向 (+z)
        axis = -axis
    return axis, center, eigvals


def _ransac_circle_2d(pts2d, iters=60, sample=3, thresh=0.005):
    """2D 点 RANSAC 拟合圆, 返回 (diameter, center2d, inlier_mask)。

    用于剖面圆拟合: 杆截面是圆, 框/滑槽的点不在圆上被剔除。
    pts2d: (N,2) 平面坐标 (米)
    thresh: 内点距离阈值 (米)
    """
    n = len(pts2d)
    if n < sample:
        return None, None, None
    best_inliers = None
    best_center = None
    best_r = None
    for _ in range(iters):
        idx = np.random.choice(n, sample, replace=False)
        p = pts2d[idx]
        # 三点定圆
        ax, ay = p[0]; bx, by = p[1]; cx, cy = p[2]
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-9:
            continue
        ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
        uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
        center = np.array([ux, uy])
        dists = np.linalg.norm(pts2d - center, axis=1)
        r = np.median(dists)
        inliers = np.abs(dists - r) < thresh
        nin = int(inliers.sum())
        if best_inliers is None or nin > best_inliers.sum():
            best_inliers = inliers
            best_center = center
            best_r = r
    if best_inliers is None or best_inliers.sum() < 3:
        return None, None, None
    return float(2.0 * best_r), best_center, best_inliers


def profile_diameter(pts, axis, center, bins=PROFILE_BINS):
    """沿轴剖分, 每段用 RANSAC 圆拟合算直径 (剔除框/滑槽离群)。

    返回 (bin_centers(bins,), diameters(bins,), seg_centers_3d(bins,) 各段截面圆心3D)
    """
    proj = (pts - center) @ axis
    pmin, pmax = proj.min(), proj.max()
    if pmax - pmin < 1e-4:
        return None, None, None
    edges = np.linspace(pmin, pmax, bins + 1)
    diameters = []
    centers = []
    seg_centers_3d = []
    for i in range(bins):
        sel = (proj >= edges[i]) & (proj < edges[i + 1])
        seg = pts[sel]
        if len(seg) < 12:
            diameters.append(0.0)
            centers.append((edges[i] + edges[i + 1]) / 2)
            seg_centers_3d.append(center + (edges[i] + edges[i + 1]) / 2 * axis)
            continue
        # 段内点投影到垂直轴的 2D 平面
        d = seg - center
        proj_seg = d @ axis
        perp = d - np.outer(proj_seg, axis)  # (N,3) 垂直轴分量
        # SVD 取 perp 两个主方向作 2D 坐标
        u, s, vh = np.linalg.svd(perp, full_matrices=False)
        pts2d = u[:, :2] * s[:2]  # (N,2) 米
        # 距离中位数 (作 fallback + 合理性校验)
        dists_seg = np.linalg.norm(perp, axis=1)
        med_diam = float(2.0 * np.median(dists_seg))
        # RANSAC 圆拟合 (杆截面圆)
        diam, c2d, _ = _ransac_circle_2d(pts2d, thresh=0.003)
        # 合理性: 杆直径应在 5~100mm, 且 RANSAC 成功
        if diam is not None and 0.005 < diam < 0.100:
            diameters.append(diam)
            c3d_perp = c2d[0] * vh[0] + c2d[1] * vh[1]
            seg_c3d = center + (edges[i] + edges[i + 1]) / 2 * axis + c3d_perp
            seg_centers_3d.append(seg_c3d)
        else:
            # RANSAC 失败或异常, 用中位数 (中位数也在合理范围才取, 否则置0)
            if 0.005 < med_diam < 0.100:
                diameters.append(med_diam)
            else:
                diameters.append(0.0)
            seg_centers_3d.append(center + (edges[i] + edges[i + 1]) / 2 * axis)
        centers.append((edges[i] + edges[i + 1]) / 2)
    return np.array(centers), np.array(diameters), np.array(seg_centers_3d)


def mask_width_profile(mask, bins=20):
    """用彩色图 mask 算沿杆主轴的像素宽度剖面 (不受深度/框污染)。

    返回 (widths(bins,), axis2d(2,), center2d(2,), proj_edges(bins+1,))
    widths: 各段像素宽度 (2×90分位垂直距离)
    """
    ys, xs = np.where(mask)
    if len(xs) < 50:
        return None, None, None, None
    pts = np.stack([xs, ys], axis=1).astype(np.float32)
    center = pts.mean(0)
    cov = np.cov(pts.T)
    _, vec = np.linalg.eigh(cov)
    axis = vec[:, -1]
    if axis[1] > 0:  # 让轴朝上(y减小), 一致方向
        axis = -axis
    proj = (pts - center) @ axis
    pmin, pmax = proj.min(), proj.max()
    if pmax - pmin < 10:
        return None, None, None, None
    edges = np.linspace(pmin, pmax, bins + 1)
    widths = []
    for i in range(bins):
        sel = (proj >= edges[i]) & (proj < edges[i + 1])
        if sel.sum() < 5:
            widths.append(0.0)
            continue
        seg = pts[sel]
        dd = seg - center
        projseg = dd @ axis
        perp = dd - np.outer(projseg, axis)
        dists = np.linalg.norm(perp, axis=1)
        widths.append(float(2.0 * np.percentile(dists, 90)))
    return np.array(widths), axis, center, edges


def find_grasp_via_mask(mask, color_bgr, depth_m, K_color, axis_rod=None, bins=20):
    """用 mask 像素宽度找粗细突变, 用点云算 3D 抓取坐标 + 姿态。

    流程:
      1. mask 宽度剖面 (视觉, 干净) 找突变段
      2. 突变段在 mask 上的像素中心 -> 反投影到 3D (用 color 内参 + depth)
      3. 姿态: Y轴=杆中轴线, X轴=相机视线在垂直Y平面的投影, Z=X×Y
      4. 返回抓取点 3D (相机系) + 姿态三轴 + 突变信息

    axis_rod: 杆中轴线方向 (相机光学系, 3,), 来自点云 PCA。None 则不算姿态。
    """
    widths, axis2d, center2d, edges = mask_width_profile(mask, bins)
    if widths is None:
        return None
    valid = widths > 0
    wv = widths[valid]
    if len(wv) < 3:
        return None

    # 平滑
    if len(wv) >= 5:
        wv_s = np.convolve(wv, np.ones(3) / 3, mode="same")
    else:
        wv_s = wv.copy()

    w_med = float(np.median(wv_s))
    w_max = float(wv_s.max())
    w_min = float(wv_s.min())
    n = len(wv_s)
    thresh = w_med * 0.15  # 阶跃阈值 (粗细交界应明显陡降)

    # 段0=图像下方, 下方1/3 常被滑槽遮挡 (渐变窄, 非真交界), 直接忽略
    # 只在后 2/3 (上 2/3) 找粗细交界
    search_lo = n // 3
    upper_w = wv_s[search_lo:]  # 后2/3的宽度
    upper_range_ratio = (upper_w.max() - upper_w.min()) / max(w_med, 1.0)

    # 异常: 后2/3宽度变化很小, 说明只看到粗端 (交界在视野外)
    if upper_range_ratio < 0.08:
        return {"error": "只看到粗端, 粗细交界不在视野内 (相机位置太靠下), 请调整相机位置",
                "mask_widths": widths}

    # 策略: 找全局最大的"粗->细"单段陡降 = 真交界
    # 遮挡是渐变 (多段缓慢降), 真交界是单段陡降 (一两段内大幅降)
    # 不强制"粗段阈值", 只找最大下降, 但要求下降后段宽度 < 中位*0.9 (确实变细)
    grads_drop = wv_s[:-1] - wv_s[1:]  # >0 表示下降(粗->细)
    thin_thresh = w_med * 0.9

    seg_type = "uniform"
    grasp_bin = n // 2
    jump_idx = -1
    found = False

    # 候选: 在后 2/3 范围找"粗->细"陡降 (下降后变细), 取下降幅度最大的
    candidates = []
    for i in range(search_lo, n - 1):
        if wv_s[i + 1] <= thin_thresh and grads_drop[i] > thresh:
            candidates.append((i, grads_drop[i]))
    if candidates:
        # 取下降幅度最大的
        candidates.sort(key=lambda x: -x[1])
        jump_idx = candidates[0][0]
        # 抓粗段一侧 (交界前1段)
        grasp_bin = max(search_lo, jump_idx - 1)
        seg_type = "thick-to-thin"
        found = True

    if not found:
        # 无明显粗->细陡降, 找细->粗上升 (可能视野只看到细->粗过渡)
        rise_candidates = []
        for i in range(search_lo, n - 1):
            if wv_s[i] <= thin_thresh and (-grads_drop[i]) > thresh:
                rise_candidates.append((i, -grads_drop[i]))
        if rise_candidates:
            rise_candidates.sort(key=lambda x: -x[1])
            jump_idx = rise_candidates[0][0]
            grasp_bin = min(n - 1, jump_idx + 2)
            seg_type = "thin-to-thick"
            found = True

    if not found:
        # 无陡变, 抓最宽区域中点 (仅在后2/3范围, 避开遮挡区)
        thick_mask = (wv_s > (w_max - (w_max - w_min) * 0.2))
        # 只取 search_lo 之后的粗段
        thick_idx = np.where(thick_mask)[0]
        thick_idx = thick_idx[thick_idx >= search_lo]
        if len(thick_idx):
            grasp_bin = int(thick_idx[len(thick_idx) // 2])
            seg_type = "thick-region"

    # grasp_bin 是 valid 过滤后的索引, 映射回原 bins 序列
    valid_idx = np.where(valid)[0]
    orig_bin = int(valid_idx[grasp_bin]) if grasp_bin < len(valid_idx) else len(valid_idx) // 2

    # 突变段在 mask 上的像素中心: 沿轴位置 edges[orig_bin] 处 + center2d
    ax_pos = (edges[orig_bin] + edges[orig_bin + 1]) / 2
    px_center = center2d + ax_pos * axis2d
    pu, pv = int(px_center[0]), int(px_center[1])

    # 反投影到 3D: 用 color 内参 + depth (depth resize 到 color 尺寸取最近邻)
    h, w = color_bgr.shape[:2]
    if depth_m.shape != (h, w):
        depth_r = cv2.resize(depth_m, (w, h), interpolation=cv2.INTER_NEAREST)
    else:
        depth_r = depth_m
    # 在像素中心附近取深度 (3x3 中位数, 抗噪)
    d_vals = []
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            yy, xx = pv + dy, pu + dx
            if 0 <= yy < h and 0 <= xx < w:
                dv = depth_r[yy, xx]
                if 0.3 < dv < 2.0:
                    d_vals.append(dv)
    if len(d_vals) < 3:
        return None
    z = float(np.median(d_vals))
    fx, fy = K_color[0, 0], K_color[1, 1]
    cx, cy = K_color[0, 2], K_color[1, 2]
    x3 = (pu - cx) * z / fx
    y3 = (pv - cy) * z / fy
    grasp_pt = np.array([x3, y3, z])

    # 突变段粗侧宽度 (像素), 估算实际直径: 用粗侧 mask 宽度 * 深度/焦距
    width_px = float(wv_s[grasp_bin]) if grasp_bin < len(wv_s) else 0
    diameter_mm = width_px * z / fx * 1000  # 像素宽度->米->mm

    # 姿态三轴 (相机光学系): Y=杆中轴, X=视线投影, Z=X×Y
    grasp_axes = None
    if axis_rod is not None:
        Y = np.asarray(axis_rod, dtype=np.float64)
        Y = Y / (np.linalg.norm(Y) + 1e-9)
        # 视线方向: 从杆指向相机原点 (相机在原点) = -grasp_pt 归一化
        view = -grasp_pt / (np.linalg.norm(grasp_pt) + 1e-9)
        # X = 视线在垂直 Y 平面的投影
        X = view - np.dot(view, Y) * Y
        Xn = np.linalg.norm(X)
        if Xn > 1e-4:
            X = X / Xn
            Z = np.cross(X, Y)
            Z = Z / (np.linalg.norm(Z) + 1e-9)
            grasp_axes = {"X": X, "Y": Y, "Z": Z}

    return {
        "grasp_pt": grasp_pt,
        "seg_type": seg_type,
        "jump_idx": jump_idx,
        "mask_widths": widths,
        "grasp_bin": orig_bin,
        "grasp_px": (pu, pv),
        "width_px": width_px,
        "diameter_mm": diameter_mm,
        "grasp_axes": grasp_axes,
    }


def find_grasp_point(diameters, seg_centers_3d):
    """找粗细交界处, 抓取点定在交界偏粗段一侧 (抓粗段)。

    用 seg_centers_3d (各段截面圆心 3D) 定位抓取点, 比纯 center+proj 更准
    (含圆心偏移, 不受杆偏离 PCA 中心影响)。

    返回 (grasp_pt(3,), seg_type, diameter_m, jump_bin_idx 或 -1)
    """
    valid = diameters > 0
    if not valid.any():
        return seg_centers_3d[0] if len(seg_centers_3d) else np.zeros(3), "unknown", 0.0, -1
    dv = diameters[valid]
    sc = seg_centers_3d[valid]
    if len(dv) < 2:
        return (sc[0] if len(sc) else np.zeros(3)), "single", float(dv[0]) if len(dv) else 0.0, -1

    if len(dv) >= 5:
        kernel = np.ones(3) / 3
        dv_s = np.convolve(dv, kernel, mode="same")
    else:
        dv_s = dv.copy()

    d_med = float(np.median(dv_s))
    d_max = float(dv_s.max())
    d_min = float(dv_s.min())

    grads = dv_s[:-1] - dv_s[1:]
    best_drop_idx = int(np.argmax(grads)) if len(grads) else -1
    best_drop_val = grads[best_drop_idx] if best_drop_idx >= 0 else 0.0
    best_rise_idx = int(np.argmin(grads)) if len(grads) else -1
    best_rise_val = -grads[best_rise_idx] if best_rise_idx >= 0 else 0.0

    jump_thresh_m = max(d_med * 0.15, 0.005)

    if best_drop_val >= best_rise_val and best_drop_val > jump_thresh_m:
        grasp_bin = max(0, best_drop_idx - 1)
        return sc[grasp_bin], "thick-to-thin", float(dv_s[grasp_bin]), best_drop_idx
    elif best_rise_val > jump_thresh_m:
        grasp_bin = min(len(sc) - 1, best_rise_idx + 2)
        return sc[grasp_bin], "thin-to-thick", float(dv_s[grasp_bin]), best_rise_idx
    else:
        if d_max - d_min > d_med * 0.2:
            thick_mask = dv_s > (d_med + (d_max - d_min) * 0.25)
            if thick_mask.any():
                thick_idx = np.where(thick_mask)[0]
                grasp_bin = int(thick_idx[len(thick_idx) // 2])
                return sc[grasp_bin], "thick-region", float(dv_s[grasp_bin]), -1
        grasp_bin = len(sc) // 2
        return sc[grasp_bin], "uniform", d_med, -1


def project_to_pixel(pt3d, K):
    """3D 相机系点 -> 像素 (光学系投影, 畸变忽略)。"""
    x, y, z = pt3d
    if z <= 0:
        return None
    u = K[0, 0] * x / z + K[0, 2]
    v = K[1, 1] * y / z + K[1, 2]
    return int(u), int(v)


def draw_axis_and_grasp(img, grasp_pt, axis, center, K, diameter_m, seg_type, jump_idx=-1,
                         bin_centers=None, diameters=None, seg_centers_3d=None, grasp_axes=None):
    """在 RGB 上画: 抓取姿态坐标系 + 杆轴 + 抓取点 + 各段直径标注 + 直径剖面。

    若 grasp_axes 给定: 画抓取姿态三轴 (X进刀红/Y杆轴绿/Z蓝), 原点=抓取点。
    否则: 画相机光学系 XYZ 轴。
    """
    out = img.copy()
    axis_len = 0.05  # 5cm

    def proj(p):
        z = p[2]
        if z <= 0.01:
            return None
        u = K[0, 0] * p[0] / z + K[0, 2]
        v = K[1, 1] * p[1] / z + K[1, 2]
        return int(u), int(v)

    # 各段直径标注 (沿杆画): 每段截面位置画垂直杆轴的短线, 标直径
    if seg_centers_3d is not None and diameters is not None:
        valid = diameters > 0
        sc = seg_centers_3d[valid]
        dv = diameters[valid]
        # 杆轴的垂直方向 (图像平面内): axis 投影到图像的垂直方向
        for i, (c3d, d) in enumerate(zip(sc, dv)):
            cp = proj(c3d)
            if cp is None:
                continue
            r = d / 2.0  # 半径(米)
            # 在垂直 axis 的平面内画直径线: 取两个垂直 axis 的方向
            # 简化: 用 axis 的垂直方向 (图像上)
            perp1 = np.array([-axis[1], axis[0], 0]) if abs(axis[0]) + abs(axis[1]) > 1e-3 else np.array([0, -axis[2], axis[1]])
            perp1 = perp1 / (np.linalg.norm(perp1) + 1e-9)
            p_a = proj(c3d + perp1 * r)
            p_b = proj(c3d - perp1 * r)
            if p_a and p_b:
                col = (0, 200, 0) if i != jump_idx else (0, 0, 255)
                cv2.line(out, p_a, p_b, col, 2)
                mid = ((p_a[0] + p_b[0]) // 2, (p_a[1] + p_b[1]) // 2)
                cv2.putText(out, f"{d*1000:.0f}", (mid[0] + 4, mid[1] - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, col, 1)

    # 抓取点处坐标系: 优先画抓取姿态三轴 (X进刀红/Y杆轴绿/Z蓝), 否则画相机光学系 XYZ
    o_px = proj(grasp_pt)
    if o_px is None:
        return out
    axis_len = 0.06  # 6cm
    if grasp_axes is not None:
        axes_to_draw = [
            (grasp_axes["X"], (0, 0, 255), "X(进刀)"),
            (grasp_axes["Y"], (0, 255, 0), "Y(杆轴)"),
            (grasp_axes["Z"], (255, 0, 0), "Z"),
        ]
    else:
        axes_to_draw = [
            (np.array([1, 0, 0]), (0, 0, 255), "X"),
            (np.array([0, 1, 0]), (0, 255, 0), "Y"),
            (np.array([0, 0, 1]), (255, 0, 0), "Z"),
        ]
    for axis_v, col, lbl in axes_to_draw:
        e = proj(grasp_pt + axis_v * axis_len)
        if e is not None:
            cv2.arrowedLine(out, o_px, e, col, 3, tipLength=0.15)
            cv2.putText(out, lbl, (e[0] + 4, e[1] + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)

    # 杆轴 (黄色)
    p1 = center + axis * 0.15
    p2 = center - axis * 0.15
    pp1, pp2 = proj(p1), proj(p2)
    if pp1 and pp2:
        cv2.line(out, pp1, pp2, (0, 255, 255), 2)

    # 抓取点
    u, v = o_px
    cv2.drawMarker(out, (u, v), (0, 0, 255), cv2.MARKER_CROSS, 28, 2)
    cv2.circle(out, (u, v), 14, (0, 0, 255), 2)
    info = f"GRASP {seg_type} d={diameter_m*1000:.1f}mm"
    info2 = f"({grasp_pt[0]*1000:.0f},{grasp_pt[1]*1000:.0f},{grasp_pt[2]*1000:.0f})mm"
    cv2.putText(out, info, (u + 18, v - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.putText(out, info2, (u + 18, v + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    # 直径剖面曲线 (左下角)
    if bin_centers is not None and diameters is not None:
        valid = diameters > 0
        if valid.any():
            dv = diameters[valid] * 1000
            gx0, gy0 = 10, out.shape[0] - 110
            gw, gh = 260, 90
            cv2.rectangle(out, (gx0, gy0), (gx0 + gw, gy0 + gh), (20, 20, 20), -1)
            dmin, dmax = float(dv.min()), float(dv.max())
            rng = max(dmax - dmin, 1.0)
            pts_plot = []
            for i, y in enumerate(dv):
                px = gx0 + int(i * gw / max(len(dv) - 1, 1))
                py = gy0 + gh - int((y - dmin) / rng * (gh - 10)) - 5
                pts_plot.append((px, py))
            for i in range(len(pts_plot) - 1):
                cv2.line(out, pts_plot[i], pts_plot[i + 1], (0, 255, 255), 1)
            if 0 <= jump_idx < len(pts_plot):
                cv2.circle(out, pts_plot[jump_idx], 4, (0, 0, 255), -1)
                cv2.putText(out, "jump", (pts_plot[jump_idx][0] + 4, pts_plot[jump_idx][1] - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
            cv2.putText(out, "diameter profile (mm)", (gx0 + 4, gy0 + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    cv2.putText(out, f"depth_z={grasp_pt[2]*1000:.0f}mm", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    return out


def main():
    args = parse_args()
    Ks, ci, di = load_intrinsics(args.config, args.camera)
    K_color = Ks["color"]
    K_depth = Ks["depth"]
    print(f"[内参] color: fx={K_color[0,0]:.1f} cy={K_color[1,2]:.1f} {ci['width']}x{ci['height']}")
    print(f"[内参] depth: fx={K_depth[0,0]:.1f} {di['width']}x{di['height']}")

    # 取帧
    if args.depth and args.color:
        color = cv2.imread(args.color)
        depth = cv2.imread(args.depth, cv2.IMREAD_ANYDEPTH).astype(np.float32) / 1000.0  # mm uint16 -> m
        print(f"[输入] color {color.shape}, depth {depth.shape}")
    else:
        color, depth = grab_one_frame(args.camera, args.config)

    # YOLO 分割
    detector = YOLODetector(args.model, names=[n.strip() for n in args.names.split(",")],
                            conf=args.conf, iou=0.45, imgsz=640, device="cpu")
    results = detector.detect(color)
    if not results:
        print("[错误] YOLO 未检测到目标")
        sys.exit(1)
    best = max(results, key=lambda r: r.mask_area_px)
    print(f"[YOLO] 检测到 {len(results)} 目标, 取最大 mask: conf={best.conf:.3f} area={best.mask_area_px}px")
    mask = best.mask

    # 点云 (用 depth 内参, depth 尺寸)
    pcd, pts = mask_to_pointcloud(color, depth, mask, K_depth)
    if pcd is None or len(pts) < 50:
        print(f"[错误] 点云不足: {0 if pts is None else len(pts)} 点")
        sys.exit(1)
    print(f"[点云] mask 区域: {len(pts)} 点")

    pcd = filter_pointcloud(pcd)
    pts = np.asarray(pcd.points)
    if len(pts) < 50:
        print(f"[错误] 滤波后点云不足: {len(pts)} 点")
        sys.exit(1)
    print(f"[滤波] 剩余 {len(pts)} 点")

    # PCA 拟合轴 (第一次, 用于背景剔除)
    axis, center, eigvals = fit_axis_pca(pts)
    print(f"[PCA1] 主轴: [{axis[0]:.3f},{axis[1]:.3f},{axis[2]:.3f}]  特征值: {eigvals.round(4)}")

    # 背景剔除 (框/滑槽点距轴远, 剔除)
    pts = remove_background(pts, axis, center)
    if len(pts) < 50:
        print(f"[错误] 背景剔除后点云不足: {len(pts)} 点")
        sys.exit(1)

    # PCA 重新拟合轴 (剔除后更准)
    axis, center, eigvals = fit_axis_pca(pts)
    print(f"[PCA2] 主轴: [{axis[0]:.3f},{axis[1]:.3f},{axis[2]:.3f}]  特征值: {eigvals.round(4)}")

    # 剖分直径 (点云 RANSAC, 供对比; 易受框污染, 仅参考)
    bin_centers, diameters, seg_centers_3d = profile_diameter(pts, axis, center)
    if bin_centers is not None:
        print(f"[直径-点云] 各段(mm): {(diameters*1000).round(1).tolist()} (参考, 易受框污染)")

    # ==== 主方案: 用 mask 像素宽度找突变 (视觉, 不受深度/框污染) + 点云算 3D 坐标 + 姿态 ====
    mask_result = find_grasp_via_mask(mask, color, depth, K_color, axis_rod=axis)
    if mask_result is None:
        print("[警告] mask 宽度分析失败, 退回点云直径方案")
        grasp_pt, seg_type, diameter_m, jump_idx = find_grasp_point(diameters, seg_centers_3d)
        seg_centers_3d_draw = seg_centers_3d
        diameters_draw = diameters
        grasp_axes = None
    elif "error" in mask_result:
        # 异常: 只看到粗端, 交界不在视野内
        print(f"[mask宽度] 各段(px): {[int(w) for w in mask_result['mask_widths']]}")
        print(f"[错误] {mask_result['error']}")
        # 仍输出可视化 (标出可见区域), 但不输出抓取点
        out = color.copy()
        overlay = color.copy(); overlay[mask] = (0, 255, 0)
        cv2.addWeighted(overlay, 0.3, out, 0.7, 0, dst=out)
        cv2.putText(out, "ERROR: " + mask_result["error"], (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.imwrite(args.out, out)
        print(f"[输出] 可视化图: {args.out}")
        sys.exit(1)
    else:
        grasp_pt = mask_result["grasp_pt"]
        seg_type = mask_result["seg_type"]
        jump_idx = mask_result["jump_idx"]
        diameter_m = mask_result["diameter_mm"] / 1000.0
        grasp_axes = mask_result.get("grasp_axes")
        print(f"[mask宽度] 各段(px): {[int(w) for w in mask_result['mask_widths']]}")
        print(f"[抓取点] 段类型={seg_type} 交界bin={jump_idx} 突变段像素宽={mask_result['width_px']:.0f}px 估算直径={diameter_m*1000:.1f}mm")
        seg_centers_3d_draw = seg_centers_3d
        diameters_draw = diameters

    print(f"[抓取点] 相机系: x={grasp_pt[0]*1000:.1f} y={grasp_pt[1]*1000:.1f} z={grasp_pt[2]*1000:.1f} mm")
    if grasp_axes is not None:
        X, Y, Z = grasp_axes["X"], grasp_axes["Y"], grasp_axes["Z"]
        print(f"[姿态] 光学系 Y(杆轴)=[{Y[0]:.3f},{Y[1]:.3f},{Y[2]:.3f}]")
        print(f"[姿态] 光学系 X(进刀)=[{X[0]:.3f},{X[1]:.3f},{X[2]:.3f}] (相机视线投影)")
        print(f"[姿态] 光学系 Z      =[{Z[0]:.3f},{Z[1]:.3f},{Z[2]:.3f}]")
        # 转 RPY (光学系, xyz 欧拉角, 度)
        R = np.column_stack([X, Y, Z])
        sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
        if sy > 1e-6:
            roll = np.degrees(np.arctan2(R[2, 1], R[2, 2]))
            pitch = np.degrees(np.arctan2(-R[2, 0], sy))
            yaw = np.degrees(np.arctan2(R[1, 0], R[0, 0]))
        else:
            roll = np.degrees(np.arctan2(-R[1, 2], R[1, 1]))
            pitch = np.degrees(np.arctan2(-R[2, 0], sy))
            yaw = 0.0
        print(f"[姿态] 光学系 RPY(度): roll={roll:.1f} pitch={pitch:.1f} yaw={yaw:.1f}")

    # 可视化 (用 color 内参投影到 color 图; 坐标系原点=抓取点; 沿杆标各段直径)
    out = draw_axis_and_grasp(color, grasp_pt, axis, center, K_color, diameter_m, seg_type,
                              jump_idx=jump_idx, bin_centers=bin_centers, diameters=diameters_draw,
                              seg_centers_3d=seg_centers_3d_draw, grasp_axes=grasp_axes)
    overlay = color.copy()
    overlay[mask] = (0, 255, 0)
    cv2.addWeighted(overlay, 0.3, out, 0.7, 0, dst=out)
    cv2.imwrite(args.out, out)
    print(f"[输出] 可视化图: {args.out}")


if __name__ == "__main__":
    main()

"""取样杆微调测量算法 (纯函数, 无 ROS/相机依赖)。

从 test_fine_tune_grasp.py 迁移: YOLO mask 中轴线 PCA + 沿杆轴深度采样。
被 camera_manager_node 的 /camera/fine_tune_measure 服务和独立测试脚本共用。
"""
import math

import cv2
import numpy as np

# ---- 算法参数 (与 test_grasp_single 的深度有效范围一致) ----
MIN_DEPTH_M = 0.3
MAX_DEPTH_M = 2.0
DEPTH_SAMPLES = 21          # 沿杆轴深度采样点数
DEPTH_SAMPLE_WIN = 5        # 每个采样点的邻域边长 (px)
MIN_DEPTH_SAMPLES = 8       # 深度采样最少有效点数
MAX_ROLL_ERR_DEG = 30.0     # 杆轴与竖直夹角超过此值视为误识别, 中止


def mask_axis(mask: np.ndarray):
    """mask 像素 PCA 求杆中轴线。返回 (axis(2,) [a_u, a_v] 且 a_v>0, center(2,)) 或 None。"""
    ys, xs = np.where(mask)
    if len(xs) < 50:
        return None
    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    center = pts.mean(axis=0)
    cov = np.cov(pts.T)
    _, vecs = np.linalg.eigh(cov)
    axis = vecs[:, -1]
    if axis[1] < 0:  # 统一朝下 (+v), 与"竖直向下"参考方向一致
        axis = -axis
    return axis, center


def measure(color: np.ndarray, depth_m: np.ndarray, mask: np.ndarray, K: np.ndarray):
    """从一帧计算微调所需的全部观测量。

    返回 dict: roll_err_deg / dy_px / dy_mm / depth_med / axis / center / u_axis_mid,
    失败返回 None。
    """
    h, w = depth_m.shape
    res = mask_axis(mask)
    if res is None:
        return None
    axis, center = res
    a_u, a_v = axis
    roll_err_deg = math.degrees(math.atan2(a_u, a_v))

    if abs(a_v) < 1e-6:
        return None
    u_axis = center[0] + (h / 2.0 - center[1]) * (a_u / a_v)
    dy_px = u_axis - w / 2.0

    # 沿杆轴采样深度 (两端各去 10%, 避开边缘)
    ys, xs = np.where(mask)
    proj = (np.stack([xs, ys], axis=1) - center) @ axis
    pmin, pmax = np.percentile(proj, 10), np.percentile(proj, 90)
    fx = K[0, 0]
    d_vals = []
    half = DEPTH_SAMPLE_WIN // 2
    for t in np.linspace(pmin, pmax, DEPTH_SAMPLES):
        pu = int(round(center[0] + t * a_u))
        pv = int(round(center[1] + t * a_v))
        for dy in range(-half, half + 1):
            for dx in range(-half, half + 1):
                yy, xx = pv + dy, pu + dx
                if 0 <= yy < h and 0 <= xx < w:
                    dv = depth_m[yy, xx]
                    if MIN_DEPTH_M < dv < MAX_DEPTH_M:
                        d_vals.append(dv)
    if len(d_vals) < MIN_DEPTH_SAMPLES:
        return None
    depth_med = float(np.median(d_vals))

    dy_mm = dy_px * depth_med / fx * 1000.0
    return {
        "roll_err_deg": roll_err_deg,
        "dy_px": float(dy_px),
        "dy_mm": dy_mm,
        "depth_med": depth_med,
        "axis": axis,
        "center": center,
        "u_axis_mid": float(u_axis),
    }


def draw_viz(color, depth_m, mask, m, out_path, title=""):
    """叠加: 深度伪彩 + mask + 中轴线 + 图像对称线 + 观测量标注。"""
    # 确保 color 是 3 通道 uint8 BGR (兼容 2D mask/灰度输入)
    if color.ndim == 2:
        out = cv2.cvtColor((color.astype(np.float32) * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    else:
        out = color.copy()
    h, w = out.shape[:2]
    valid = (depth_m > MIN_DEPTH_M) & (depth_m < MAX_DEPTH_M)
    d = np.clip(depth_m, MIN_DEPTH_M, MAX_DEPTH_M)
    norm = ((d - MIN_DEPTH_M) / (MAX_DEPTH_M - MIN_DEPTH_M + 1e-6) * 255).astype(np.uint8)
    colored = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    colored[~valid] = 0
    out = cv2.addWeighted(out, 0.65, colored, 0.35, 0)
    overlay = out.copy()
    overlay[mask] = (0, 255, 0)
    out = cv2.addWeighted(overlay, 0.3, out, 0.7, 0)
    cv2.line(out, (w // 2, 0), (w // 2, h), (0, 255, 255), 1)
    a_u, a_v = m["axis"]
    cu, cv = m["center"]
    if abs(a_v) > 1e-6:
        p_top = (int(cu + (0 - cv) * a_u / a_v), 0)
        p_bot = (int(cu + (h - cv) * a_u / a_v), h)
        cv2.line(out, p_top, p_bot, (0, 0, 255), 2)
    cv2.drawMarker(out, (int(m["u_axis_mid"]), h // 2), (255, 0, 255),
                   cv2.MARKER_CROSS, 20, 2)
    lines = [
        f"roll_err={m['roll_err_deg']:+.2f}deg",
        f"dy={m['dy_mm']:+.1f}mm ({m['dy_px']:+.1f}px)",
        f"depth_med={m['depth_med']*1000:.0f}mm",
    ]
    if title:
        lines.insert(0, title)
    for i, line in enumerate(lines):
        cv2.putText(out, line, (10, 28 + i * 26), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 255, 0), 2)
    cv2.imwrite(out_path, out)


def load_fine_tune_cfg(config_path: str, camera_id: str) -> dict:
    """读 camera_config.yaml 中该相机的 fine_tune 偏移/符号配置 (缺省 0/1)。"""
    import yaml
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    cam = next(c for c in cfg["cameras"] if c["id"] == camera_id)
    ft = cam.get("fine_tune") or {}
    return {
        "cam_y_offset_mm": float(ft.get("cam_y_offset_mm", 0.0)),
        "depth_offset_mm": float(ft.get("depth_offset_mm", 0.0)),
        "roll_sign": float(ft.get("roll_sign", 1.0)),
        "y_sign": float(ft.get("y_sign", 1.0)),
        "z_sign": float(ft.get("z_sign", 1.0)),
    }

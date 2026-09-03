"""fine_tune_measure 纯算法单元测试 (合成 mask + 合成深度图, 无相机/ROS)。"""
import os
import numpy as np
import yaml

from python_pkgs.orbbec_vision.fine_tune_measure import (
    mask_axis, measure, draw_viz, load_fine_tune_cfg,
)

W, H = 1280, 720
FX = 600.0
K = np.array([[FX, 0, W / 2], [0, FX, H / 2], [0, 0, 1]])


def synth_mask(u_center=W / 2, tilt_deg=0.0, v0=100, v1=600, width=12):
    """合成杆 mask: v0..v1 的斜条, 杆轴与图像竖直方向夹角 tilt_deg (正=向下偏右)。"""
    mask = np.zeros((H, W), dtype=bool)
    tan_t = np.tan(np.radians(tilt_deg))
    for v in range(v0, v1):
        u = int(round(u_center + tan_t * (v - H / 2)))
        mask[v, u - width // 2:u + width // 2] = True
    return mask


def synth_depth(depth_m=0.5):
    return np.full((H, W), depth_m, dtype=np.float32)


def test_mask_axis_vertical():
    axis, center = mask_axis(synth_mask())
    assert abs(axis[0]) < 0.01 and axis[1] > 0
    assert abs(center[0] - W / 2) < 1.0


def test_measure_straight_centered():
    mask = synth_mask()
    m = measure(mask, synth_depth(), mask, K)
    assert m is not None
    assert abs(m["roll_err_deg"]) < 0.5
    assert abs(m["dy_px"]) < 1.0
    assert abs(m["dy_mm"]) < 1.0
    assert abs(m["depth_med"] - 0.5) < 0.005


def test_measure_roll_tilted():
    m = measure(synth_mask(tilt_deg=5.0), synth_depth(), synth_mask(tilt_deg=5.0), K)
    assert m is not None
    assert 4.0 < m["roll_err_deg"] < 6.0


def test_measure_dy_offset():
    du = 20.0
    mask = synth_mask(u_center=W / 2 + du)
    m = measure(mask, synth_depth(), mask, K)
    assert m is not None
    assert abs(m["dy_px"] - du) < 1.0
    # dy_mm = dy_px * depth / fx * 1000
    assert abs(m["dy_mm"] - (du * 0.5 / FX * 1000)) < 1.0


def test_measure_depth_with_holes():
    depth = synth_depth(0.5)
    depth[:, :400] = 0.0  # 左半无效, 杆在中央不受影响
    mask = synth_mask()
    m = measure(mask, depth, mask, K)
    assert m is not None
    assert abs(m["depth_med"] - 0.5) < 0.005


def test_measure_depth_all_invalid():
    mask = synth_mask()
    assert measure(mask, np.zeros((H, W), dtype=np.float32), mask, K) is None


def test_mask_too_small():
    mask = np.zeros((H, W), dtype=bool)
    mask[100, 100] = True  # < 50 px
    assert mask_axis(mask) is None
    assert measure(mask, synth_depth(), mask, K) is None


def test_measure_horizontal_axis_returns_none():
    mask = np.zeros((H, W), dtype=bool)
    mask[300:312, 200:1000] = True  # 水平条 -> a_v≈0
    assert measure(mask, synth_depth(), mask, K) is None


def test_draw_viz_writes_file(tmp_path):
    mask = synth_mask(tilt_deg=3.0)
    m = measure(mask, synth_depth(), mask, K)
    out = str(tmp_path / "viz.jpg")
    draw_viz(synth_mask(), synth_depth(), mask, m, out, title="test")
    assert os.path.isfile(out) and os.path.getsize(out) > 0


def test_load_fine_tune_cfg(tmp_path):
    cfg = {"cameras": [
        {"id": "right_arm", "fine_tune": {
            "cam_y_offset_mm": 5.0, "depth_offset_mm": -3.0,
            "roll_sign": -1.0, "y_sign": 1.0, "z_sign": 1.0}},
        {"id": "head"},
    ]}
    p = tmp_path / "camera_config.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    ft = load_fine_tune_cfg(str(p), "right_arm")
    assert ft["cam_y_offset_mm"] == 5.0
    assert ft["depth_offset_mm"] == -3.0
    assert ft["roll_sign"] == -1.0
    ft_head = load_fine_tune_cfg(str(p), "head")
    assert ft_head == {"cam_y_offset_mm": 0.0, "depth_offset_mm": 0.0,
                       "roll_sign": 1.0, "y_sign": 1.0, "z_sign": 1.0}

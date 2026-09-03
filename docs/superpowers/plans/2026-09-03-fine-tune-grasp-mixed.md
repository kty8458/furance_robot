# 取样杆闭环微调集成混合控制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已验证的 YOLO+深度取样杆三阶段闭环微调功能（`test_fine_tune_grasp.py`）集成进工作流 `mixed` 步骤，测量经相机管理节点完成，不再直连相机。

**Architecture:** 方案 A——`camera_manager_node` 新增 `/camera/fine_tune_measure` 测量服务（对齐取帧 + YOLO + 测量算法，只返回数字），闭环编排放 `mixed_execution/functions/fine_tune_grasp.py`（通过 `ctx.ros_call` 测量、`ctx.ros_call_typed` 调 MoveP 运动臂、`ctx.tf_lookup` 查 TF）。工作流引擎零改动。

**Tech Stack:** Python 3.10 / rclpy / pyorbbecsdk / onnxruntime(YOLODetector) / numpy / pytest

**Spec:** `docs/superpowers/specs/2026-09-03-fine-tune-grasp-mixed-design.md`

## Global Constraints

- 单位约定（与现有一致）：深度米、dy 毫米、角度度、位姿矩阵 4x4 米。
- pyorbbecsdk 仅在 `camera_manager_node` 进程内使用，任何新代码不得跨进程直连相机。
- 提交格式 `<type>: <message>`（CLAUDE.md）。
- 不修改 `shared/` 包。
- 仓库根：`/home/jetson/Desktop/furance_robot`（下文相对路径均基于此）。所有 shell 命令默认在仓库根执行。
- pytest 直接跑文件路径（这些 ROS 包没有 ament test 集成），需要先 `source install/setup.bash`（control_interfaces 等）。
- **不要用 Read 工具读取任何图片文件**（jpg/png，接口不支持）；验证可视化输出只用 `ls -la <路径>` 确认存在和大小。
- ROS2 服务统一 `furance_interfaces/srv/GenericCommand`：Request `{command, params_json}`，Response `{success, message, result_json}`。
- 修改 orbbec_vision / mixed_execution 后需 `cd ros2_ws && colcon build --packages-select python_pkgs mixed_execution` 并重启节点才生效。

---

### Task 1: `fine_tune_measure.py` 测量算法库 + 单元测试

从 `test_fine_tune_grasp.py` 迁移纯算法到独立库模块（无 pyorbbecsdk、无 rclpy 依赖），TDD。

**Files:**
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/fine_tune_measure.py`
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/tests/__init__.py`（空文件）
- Test: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/tests/test_fine_tune_measure.py`

**Interfaces:**
- Produces（后续 Task 2/4 依赖，签名必须一致）:
  - 常量 `MIN_DEPTH_M=0.3`, `MAX_DEPTH_M=2.0`, `MAX_ROLL_ERR_DEG=30.0`
  - `mask_axis(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None`（axis(2,) 且 a_v>0, center(2,)）
  - `measure(color, depth_m, mask, K) -> dict | None`，dict 键：`roll_err_deg`, `dy_px`, `dy_mm`, `depth_med`, `axis`, `center`, `u_axis_mid`
  - `draw_viz(color, depth_m, mask, m, out_path, title="") -> None`
  - `load_fine_tune_cfg(config_path: str, camera_id: str) -> dict`，键：`cam_y_offset_mm`, `depth_offset_mm`, `roll_sign`, `y_sign`, `z_sign`（缺省 0.0/1.0）

- [ ] **Step 1: 写失败测试**

`tests/test_fine_tune_measure.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /home/jetson/Desktop/furance_robot/ros2_ws/src/t1_robot/python_pkgs && python3 -m pytest python_pkgs/orbbec_vision/tests/test_fine_tune_measure.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'python_pkgs.orbbec_vision.fine_tune_measure'`

- [ ] **Step 3: 实现算法库**

`fine_tune_measure.py`——从 `test_fine_tune_grasp.py` 原样迁移算法（注意：**不得** import `test_grasp_single`，它会拉入 pyorbbecsdk；常量独立定义）：

```python
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
```

- [ ] **Step 4: 运行确认通过**

同 Step 2 命令。Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
cd /home/jetson/Desktop/furance_robot && git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/fine_tune_measure.py ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/tests/ && git commit -m "feat: 取样杆微调测量算法库 fine_tune_measure"
```

---

### Task 2: 测试脚本改用算法库

`test_fine_tune_grasp.py` 删除与 `fine_tune_measure.py` 重复的代码，改为 import。脚本保留用于真机调试（直连相机模式不变）。

**Files:**
- Modify: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/test_fine_tune_grasp.py`

**Interfaces:**
- Consumes: Task 1 的 `fine_tune_measure` 模块（mask_axis/measure/draw_viz/load_fine_tune_cfg/常量）
- Produces: 无（后续任务不依赖本文件）

- [ ] **Step 1: 删除重复定义，改为 import**

在 `test_fine_tune_grasp.py` 中：

1. 文件头 import 区（`from test_grasp_single import ...` 之后）加：

```python
from fine_tune_measure import (
    MAX_ROLL_ERR_DEG, mask_axis, measure, draw_viz, load_fine_tune_cfg,
)
```

（脚本已有 `sys.path.insert(0, _here)`，同目录 import 可用；不要用 `python_pkgs.orbbec_vision.` 前缀——脚本常被直接运行。）

2. 删除以下重复定义（原样搬进库里的那些）：
   - 算法常量块：`DEPTH_SAMPLES`、`DEPTH_SAMPLE_WIN`、`MIN_DEPTH_SAMPLES`、`MAX_ROLL_ERR_DEG`（约 61-65 行）
   - `def mask_axis(...)` 整个函数
   - `def measure(...)` 整个函数
   - `def draw_viz(...)` 整个函数
   - `def load_fine_tune_cfg(...)` 整个函数
3. `measure_once()` 中对 `MAX_ROLL_ERR_DEG` 的引用不变（现在来自 import）。
4. 注意保留：`CameraGrabber`（仍从 `test_grasp_single` import `_frame_to_bgr`/`_frame_to_depth_mm`，直连模式不变）、位姿数学函数、`ArmInterface`、`main()`。
5. `main()` 中 `ft = load_fine_tune_cfg(args.config, args.camera)` 调用不变（签名一致）。

- [ ] **Step 2: 语法与导入验证**

```bash
cd /home/jetson/Desktop/furance_robot/ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision && python3 test_fine_tune_grasp.py --help
```
Expected: 打印 usage（含 `--ref-depth` 等），无 ImportError。

- [ ] **Step 3: Commit**

```bash
cd /home/jetson/Desktop/furance_robot && git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/test_fine_tune_grasp.py && git commit -m "refactor: 测试脚本复用 fine_tune_measure 算法库"
```

---

### Task 3: `CameraManager.grab_aligned` 对齐取帧 + per-camera 测量锁

给 `CameraManager` 增加测量专用取帧能力（接管 pipeline → color+depth+FULL_FRAME_REQUIRE + AlignFilter → 恢复），并用 per-camera RLock 防止测量与推流启停抢 pipeline。硬件相关，无法单测；验证靠 py_compile，真机验证在 Task 7。

**Files:**
- Modify: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_manager_node.py`（`CameraManager.__init__` 约 375-391 行、`_init_cameras` 约 522-527 行、`start_stream` 535-583 行、`stop_stream` 585-602 行，之后新增 `grab_aligned` 方法）

**Interfaces:**
- Produces（Task 4 依赖）:
  - `CameraManager._measure_locks: dict[str, threading.RLock]`
  - `CameraManager.grab_aligned(camera_id: str, settle_frames: int = 15, settle_sec: float = 0.6, timeout: float = 10.0) -> dict`
    返回 `{success: True, color: np.ndarray(BGR), depth: np.ndarray(米 float32)}` 或 `{success: False, message: str}`

- [ ] **Step 1: `__init__` 加锁字典**

在 `CameraManager.__init__` 中 `self._ae_info ...` 行之后加：

```python
        self._measure_locks: dict[str, threading.RLock] = {}  # 测量接管 pipeline 期间阻塞该相机推流启停
```

- [ ] **Step 2: `_init_cameras` 初始化每个相机的锁**

在 `_init_cameras` 中 `self._ws_subscribers[cid] = set()` 之后加：

```python
            self._measure_locks[cid] = threading.RLock()
```

- [ ] **Step 3: `start_stream` / `stop_stream` 加锁**

将 `start_stream` 的参数检查之后到方法结束的全部逻辑包进 `with self._measure_locks[camera_id]:`（整体缩进一级）。方法开头改为：

```python
    def start_stream(self, camera_id: str, stream_type: str = "raw") -> dict:
        if camera_id not in self._cameras:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}
        if not self._cameras[camera_id].connected:
            return {"success": False, "message": f"Not connected: {camera_id}"}
        with self._measure_locks[camera_id]:
            # ...(原 if self._streaming[camera_id]: 起的全部逻辑, 整体缩进)...
```

`stop_stream` 同理：

```python
    def stop_stream(self, camera_id: str) -> dict:
        if camera_id not in self._cameras:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}
        with self._measure_locks[camera_id]:
            # ...(原 self._streaming[camera_id] = False 起的全部逻辑, 整体缩进)...
```

（用 RLock 是因为 `grab_aligned` 持锁期间会调 `stop_stream`/`start_stream`，同线程重入。）

- [ ] **Step 4: 新增 `grab_aligned` 方法**

加在 `stop_stream` 之后（`_set_ae_property` 之前）：

```python
    def grab_aligned(self, camera_id: str, settle_frames: int = 15,
                     settle_sec: float = 0.6, timeout: float = 10.0) -> dict:
        """测量专用取帧: color+depth + FULL_FRAME_REQUIRE, AlignFilter 对齐。

        接管该相机 pipeline (停推流→重启为对齐模式→取帧→恢复原流状态)。
        settle 逻辑同测试脚本: 丢 settle_frames 帧 + 距调用起 settle_sec 秒,
        保证取到的是调用时刻之后的新画面 (闭环中臂刚停稳, 旧帧会污染测量)。
        返回 {success, color(BGR), depth(米)} 或 {success: False, message}。
        """
        from pyorbbecsdk import (Config, OBSensorType, OBFormat, OBError,
                                 OBFrameAggregateOutputMode, AlignFilter, OBStreamType)
        lock = self._measure_locks.get(camera_id)
        if lock is None:
            return {"success": False, "message": f"Unknown camera: {camera_id}"}
        with lock:
            was_streaming = self._streaming.get(camera_id, False)
            prev_type = self._stream_types.get(camera_id, "raw")
            if was_streaming:
                self.stop_stream(camera_id)
            try:
                pipeline = self._pipelines.get(camera_id)
                if pipeline is None:
                    return {"success": False, "message": f"No pipeline: {camera_id}"}
                config = Config()
                try:
                    cp = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR) \
                        .get_video_stream_profile(0, 0, OBFormat.RGB, 0)
                except Exception:
                    cp = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR) \
                        .get_default_video_stream_profile()
                config.enable_stream(cp)
                try:
                    dp = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR) \
                        .get_video_stream_profile(0, 0, OBFormat.Y16, 0)
                except Exception:
                    dp = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR) \
                        .get_default_video_stream_profile()
                config.enable_stream(dp)
                try:
                    config.set_frame_aggregate_output_mode(
                        OBFrameAggregateOutputMode.FULL_FRAME_REQUIRE)
                except Exception:
                    pass
                try:
                    pipeline.start(config)
                except OBError as e:
                    return {"success": False, "message": f"Pipeline start failed: {e}"}

                try:
                    align = AlignFilter(align_to_stream=OBStreamType.COLOR_STREAM)
                    got = 0
                    color = depth = None
                    t0 = time.time()
                    while time.time() - t0 < timeout:
                        frames = pipeline.wait_for_frames(1000)
                        if frames is None:
                            continue
                        try:
                            aligned = align.process(frames)
                        except Exception:
                            continue
                        if not aligned:
                            continue
                        try:
                            aligned = aligned.as_frame_set()
                        except Exception:
                            pass
                        cf = aligned.get_color_frame()
                        df = aligned.get_depth_frame()
                        if cf is not None and df is not None:
                            c = self._to_bgr(cf)
                            d = self._to_depth_mm(df)
                            if c is not None and d is not None:
                                color, depth = c, d / 1000.0  # mm -> 米
                                got += 1
                                if got > settle_frames and time.time() - t0 >= settle_sec:
                                    return {"success": True, "color": color, "depth": depth}
                    return {"success": False,
                            "message": "取帧失败 (AlignFilter depth->color 超时)"}
                finally:
                    try:
                        pipeline.stop()
                    except Exception:
                        pass
            finally:
                if was_streaming:
                    try:
                        self.start_stream(camera_id, prev_type)
                    except Exception:
                        logger.exception("恢复推流失败: %s", camera_id)
```

- [ ] **Step 5: 语法验证**

```bash
cd /home/jetson/Desktop/furance_robot && python3 -m py_compile ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_manager_node.py && echo OK
```
Expected: OK

- [ ] **Step 6: Commit**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_manager_node.py && git commit -m "feat: CameraManager 对齐取帧 grab_aligned 与测量互斥锁"
```

---

### Task 4: `/camera/fine_tune_measure` 服务

在 `camera_manager_node.py` 的 `main()` 中新增服务 handler：取帧 → YOLO → 测量 → 返回数字 + fine_tune 配置 + 可视化路径。

**Files:**
- Modify: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_manager_node.py`（`main()` 中 `node.create_service(GenericCommand, "/camera/compute_pose", ...)` 约 1920 行之后）

**Interfaces:**
- Consumes: Task 1 的 `measure`/`draw_viz`/`load_fine_tune_cfg`/`MAX_ROLL_ERR_DEG`；Task 3 的 `manager.grab_aligned`；`manager._yolo_detectors[camera_id]`（detect 返回带 `.conf`/`.mask`/`.mask_area_px` 的结果列表）；`_cam_configs[camera_id]["calibration"]["color_intrinsics"]`；`_config_dir`
- Produces（Task 6 依赖的服务契约）:
  - 服务 `/camera/fine_tune_measure`，params_json：`{"camera_id": str, "settle_frames": int=15, "settle_sec": float=0.6, "save_viz": bool=true}`
  - 成功 result_json：`{"camera_id", "roll_err_deg", "dy_px", "dy_mm", "depth_med", "conf", "mask_area_px", "viz_path", "fine_tune": {"cam_y_offset_mm", "depth_offset_mm", "roll_sign", "y_sign", "z_sign"}}`
  - 失败：`success=False, message=<原因>`（YOLO 未检测到 / 中轴线计算失败 / 误识别超 30° / 取帧超时等）

- [ ] **Step 1: 新增 handler 并注册服务**

在 `node.create_service(GenericCommand, "/camera/compute_pose", _handle_compute_pose)` 之后加：

```python
    # /camera/fine_tune_measure (GenericCommand) — 取样杆微调单次测量
    def _handle_fine_tune_measure(request, response):
        import time as _time
        from python_pkgs.orbbec_vision.fine_tune_measure import (
            measure as ft_measure, draw_viz, load_fine_tune_cfg, MAX_ROLL_ERR_DEG,
        )
        params = json.loads(request.params_json) if request.params_json else {}
        camera_id = params.get("camera_id", "")
        settle_frames = int(params.get("settle_frames", 15))
        settle_sec = float(params.get("settle_sec", 0.6))
        save_viz = bool(params.get("save_viz", True))

        def _fail(msg):
            response.success = False
            response.message = msg
            response.result_json = "{}"
            return response

        cam_info = manager._cameras.get(camera_id)
        if camera_id not in _cam_configs or cam_info is None or not cam_info.connected:
            return _fail(f"相机不可用: {camera_id}")
        detector = manager._yolo_detectors.get(camera_id)
        if detector is None:
            return _fail(f"YOLO 检测器不可用: {camera_id} (检查 yolo_config.yaml)")

        # 1. 对齐取帧 (per-camera 锁, 期间推流排队)
        grab = manager.grab_aligned(camera_id, settle_frames, settle_sec)
        if not grab["success"]:
            return _fail(grab["message"])
        color, depth_m = grab["color"], grab["depth"]

        # 2. YOLO 分割 (复用 mask 流的 detector), 取 mask 最大者
        results = detector.detect(color)
        if not results:
            return _fail("YOLO 未检测到取样杆")
        best = max(results, key=lambda r: r.mask_area_px)

        # 3. 测量
        ci = _cam_configs[camera_id]["calibration"]["color_intrinsics"]
        K = np.array([[ci["fx"], 0, ci["cx"]],
                      [0, ci["fy"], ci["cy"]],
                      [0, 0, 1]], dtype=np.float64)
        m = ft_measure(color, depth_m, best.mask, K)
        if m is None:
            return _fail("mask 中轴线/深度计算失败")
        if abs(m["roll_err_deg"]) > MAX_ROLL_ERR_DEG:
            return _fail(f"杆轴与竖直夹角 {m['roll_err_deg']:.1f}° 超过 "
                         f"{MAX_ROLL_ERR_DEG}°, 疑似误识别")

        # 4. 可视化 (失败不影响测量结果)
        viz_path = ""
        if save_viz:
            out_dir = os.path.join(_config_dir, "data", "fine_tune",
                                   _time.strftime("%Y%m%d_%H%M%S"))
            os.makedirs(out_dir, exist_ok=True)
            viz_path = os.path.join(out_dir, "measure.jpg")
            try:
                draw_viz(color, depth_m, best.mask, m, viz_path,
                         title=f"{camera_id} measure")
            except Exception:
                logger.exception("fine_tune 可视化保存失败")
                viz_path = ""

        # 5. fine_tune 偏移/符号一并返回 (单一配置来源, 调用方不解析 yaml)
        result = {
            "camera_id": camera_id,
            "roll_err_deg": m["roll_err_deg"],
            "dy_px": m["dy_px"],
            "dy_mm": m["dy_mm"],
            "depth_med": m["depth_med"],
            "conf": float(best.conf),
            "mask_area_px": int(best.mask_area_px),
            "viz_path": viz_path,
            "fine_tune": load_fine_tune_cfg(config_path, camera_id),
        }
        response.success = True
        response.message = "OK"
        response.result_json = json.dumps(result)
        return response

    node.create_service(GenericCommand, "/camera/fine_tune_measure",
                        _handle_fine_tune_measure)
```

（`json`/`os`/`np`/`logger`/`config_path`/`_cam_configs`/`_config_dir` 均在 `main()` 作用域内已有。）

- [ ] **Step 2: 语法验证 + 构建**

```bash
cd /home/jetson/Desktop/furance_robot && python3 -m py_compile ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_manager_node.py && cd ros2_ws && colcon build --packages-select python_pkgs
```
Expected: 编译 OK，colcon build 成功。

- [ ] **Step 3: Commit**

```bash
cd /home/jetson/Desktop/furance_robot && git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_manager_node.py && git commit -m "feat: /camera/fine_tune_measure 测量服务"
```

---

### Task 5: mixed_execution 框架扩展（类型化服务 + TF）

`RosCaller` 支持任意 srv 类型（MoveP），节点加 TF listener，`ExecutionContext` 暴露 `ctx.ros_call_typed` / `ctx.tf_lookup`。ROS 粘合代码，验证靠 py_compile + colcon build；行为由 Task 6 的 mock 测试覆盖。

**Files:**
- Modify: `ros2_ws/src/mixed_execution/mixed_execution/mixed_executor_node.py`（RosCaller 类、main()）
- Modify: `ros2_ws/src/mixed_execution/mixed_execution/executor.py`（ExecutionContext、MixedExecutor）
- Modify: `ros2_ws/src/mixed_execution/package.xml`

**Interfaces:**
- Produces（Task 6 依赖）:
  - `RosCaller.call_typed(service_name: str, srv_type, request, timeout: float = 30.0)` → 原生 response 对象；失败/超时返回 None
  - `ctx.ros_call_typed(service_name, srv_type, request, timeout=30.0)` → 同上
  - `ctx.tf_lookup(parent: str, child: str, timeout: float = 2.0)` → `(t_xyz: np.ndarray(3,), q_xyzw: np.ndarray(4,))` 或 None
  - `ctx.ros_call(service, params, timeout=30.0)` → 不变（原本就透传 timeout）

- [ ] **Step 1: `RosCaller.call_typed`**

在 `mixed_executor_node.py` 的 `RosCaller.call` 方法之后加：

```python
    def call_typed(self, service_name: str, srv_type, request,
                   timeout: float = SERVICE_TIMEOUT):
        """调用任意类型 ROS2 服务 (如 control_interfaces/srv/MoveP)。

        request 为已构建的 srv.Request, 返回原生 response;
        服务不可用/超时/异常返回 None (原因见日志)。
        """
        with self._lock:
            client = self._clients.get(service_name)
            if client is None:
                client = self._node.create_client(srv_type, service_name)
                self._clients[service_name] = client
        if not client.wait_for_service(timeout_sec=2.0):
            logger.warning("Service not available: %s", service_name)
            return None
        future = client.call_async(request)
        deadline = time.time() + timeout
        while not future.done() and time.time() < deadline:
            time.sleep(0.02)
        if not future.done():
            logger.warning("Service call timeout: %s", service_name)
            return None
        try:
            return future.result()
        except Exception as e:
            logger.warning("Service call failed: %s: %s", service_name, e)
            return None
```

- [ ] **Step 2: main() 加 TF listener 与 _tf_lookup**

在 `main()` 中 `ros_caller = RosCaller(node)` 之前加（文件顶部已有 rclpy import；需补 `import numpy as np`）：

```python
    import tf2_ros
    _tf_buffer = tf2_ros.Buffer()
    tf2_ros.TransformListener(_tf_buffer, node)

    def _tf_lookup(parent: str, child: str, timeout: float = 2.0):
        """查 TF parent->child, 返回 (t_xyz(3,), q_xyzw(4,)) 或 None。

        工作线程调用; 主线程 spin 处理 TF 回调。位姿数学 (转 4x4) 由功能脚本
        自己完成, 这里只给原始平移+四元数。
        """
        from rclpy.duration import Duration
        try:
            msg = _tf_buffer.lookup_transform(parent, child, rclpy.time.Time(),
                                              timeout=Duration(seconds=timeout))
        except Exception as e:
            logger.warning("TF lookup %s->%s failed: %s", parent, child, e)
            return None
        t = msg.transform.translation
        q = msg.transform.rotation
        return (np.array([t.x, t.y, t.z]),
                np.array([q.x, q.y, q.z, q.w]))
```

`executor = MixedExecutor(...)` 行改为：

```python
    executor = MixedExecutor(chassis=chassis, ros_call=ros_caller.call,
                             ros_call_typed=ros_caller.call_typed,
                             tf_lookup=_tf_lookup)
```

- [ ] **Step 3: executor.py 扩展**

`ExecutionContext.__init__` 加两个可选参数并赋属性（放在 `ros_call` 之后）：

```python
    def __init__(self, execution_id: str, params: dict,
                 cancel_event: threading.Event,
                 chassis: Optional[ChassisHttpClient] = None,
                 ros_call: Optional[Callable] = None,
                 ros_call_typed: Optional[Callable] = None,
                 tf_lookup: Optional[Callable] = None):
        ...
        self.ros_call = ros_call
        self.ros_call_typed = ros_call_typed
        self.tf_lookup = tf_lookup
```

类 docstring 的 ctx 能力列表同步补两行：

```
      ctx.ros_call_typed(srv, type, req) 调用任意类型 ROS2 服务 (可选)
      ctx.tf_lookup(parent, child)      TF 查询, 返回 (t, q) 或 None (可选)
```

`MixedExecutor.__init__` 同样加 `ros_call_typed`/`tf_lookup` 可选参数存为属性；`start()` 中构造 ctx 时传入：

```python
        ctx = ExecutionContext(execution_id, params, cancel_event,
                               chassis=self._chassis, ros_call=self._ros_call,
                               ros_call_typed=self._ros_call_typed,
                               tf_lookup=self._tf_lookup)
```

- [ ] **Step 4: package.xml 加依赖**

`<exec_depend>furance_interfaces</exec_depend>` 之后加：

```xml
  <exec_depend>control_interfaces</exec_depend>
  <exec_depend>tf2_ros</exec_depend>
```

- [ ] **Step 5: 验证 + 构建**

```bash
cd /home/jetson/Desktop/furance_robot && python3 -m py_compile ros2_ws/src/mixed_execution/mixed_execution/mixed_executor_node.py ros2_ws/src/mixed_execution/mixed_execution/executor.py && cd ros2_ws && colcon build --packages-select mixed_execution
```
Expected: OK + build 成功。

- [ ] **Step 6: Commit**

```bash
cd /home/jetson/Desktop/furance_robot && git add ros2_ws/src/mixed_execution/ && git commit -m "feat: mixed_execution 支持类型化服务与 TF 查询"
```

---

### Task 6: `functions/fine_tune_grasp.py` 闭环功能 + mock 状态机测试

三阶段闭环编排，从 `test_fine_tune_grasp.py` 的 `main()` 迁移，基础设施换成 ctx。TDD：先写 mock ctx 测试。

**Files:**
- Create: `ros2_ws/src/mixed_execution/mixed_execution/functions/fine_tune_grasp.py`
- Modify: `ros2_ws/src/mixed_execution/mixed_execution/functions/__init__.py`（注册 import）
- Create: `ros2_ws/src/mixed_execution/test/test_fine_tune_grasp.py`
- Create: `ros2_ws/src/mixed_execution/test/__init__.py`（空文件）

**Interfaces:**
- Consumes: Task 4 服务契约（`/camera/fine_tune_measure` 的 result_json 结构）；Task 5 的 `ctx.ros_call_typed` / `ctx.tf_lookup`；`/move_pose`（`control_interfaces/srv/MoveP`：`req.lor`/`req.to_frame`/`req.reference_frame`/`req.planner`/`req.target_pose`，resp `.success`/`.message`）；`control_interfaces.srv.MoveP`、`geometry_msgs.msg.PoseStamped`
- Produces:
  - mixed function `fine_tune_grasp(ctx, camera="right_arm", arm="right", ref_depth=None, max_iter=3, roll_tol=1.0, y_tol=2.0, depth_tol=0.030, dry_run=False)`
  - 成功返回 dict：`{"converged": bool, "iterations": {"roll": int, "y": int}, "final": {"roll_err_deg", "dy_eff_mm", "dz_mm"}, "viz_paths": [str]}`
  - 失败抛 `FineTuneError`（executor 捕获后 state=failed）；取消抛 `MixedCancelled`
  - 阶段3 深度进给用的是**阶段2 最后一次测量的 depth_med**（与脚本一致，不另取帧）

- [ ] **Step 1: 写失败测试**

`test/test_fine_tune_grasp.py`：

```python
"""fine_tune_grasp 闭环状态机测试 (mock ctx, 无 ROS 服务/相机/臂)。"""
import numpy as np
import pytest
from types import SimpleNamespace

from mixed_execution.executor import MixedCancelled
from mixed_execution.functions.fine_tune_grasp import (
    fine_tune_grasp, FineTuneError, _R_to_quat, _rpy_to_R,
)

FT = {"cam_y_offset_mm": 2.0, "depth_offset_mm": 0.0,
      "roll_sign": 1.0, "y_sign": 1.0, "z_sign": 1.0}


def m_data(roll=0.1, dy_mm=1.0, depth=0.50):
    """一次测量的服务返回 data。"""
    return {"roll_err_deg": roll, "dy_px": 5.0, "dy_mm": dy_mm,
            "depth_med": depth, "conf": 0.9, "mask_area_px": 5000,
            "viz_path": "", "fine_tune": dict(FT)}


class FakeCtx:
    """按预置序列回放测量结果; 记录 move 请求; TF 恒为单位位姿。"""

    def __init__(self, measures):
        self.measures = list(measures)
        self.moves = []          # 记录 MoveP.Request
        self.cancelled = False
        self.progress = []

    def ros_call(self, service, params, timeout=None):
        assert service == "/camera/fine_tune_measure"
        assert len(self.measures) > 0, "测量次数超出预置序列"
        return {"success": True, "message": "OK", "data": self.measures.pop(0)}

    def ros_call_typed(self, service, srv_type, request, timeout=None):
        assert service == "/move_pose"
        self.moves.append(request)
        return SimpleNamespace(success=True, message="")

    def tf_lookup(self, parent, child, timeout=2.0):
        return (np.zeros(3), np.array([0.0, 0.0, 0.0, 1.0]))  # 单位位姿

    def set_progress(self, pct, message=""):
        self.progress.append((pct, message))

    def check_cancel(self):
        if self.cancelled:
            raise MixedCancelled("Cancelled by user")


def test_all_converged_no_move():
    ctx = FakeCtx([m_data(roll=0.2, dy_mm=2.5),   # 阶段1: 已收敛 (dy 不看)
                   m_data(roll=0.1, dy_mm=2.5)])  # 阶段2: dy_eff=0.5 < y_tol 收敛
    r = fine_tune_grasp(ctx, camera="right_arm", arm="right", ref_depth=0.50)
    assert r["converged"] is True
    assert r["iterations"] == {"roll": 1, "y": 1}
    assert len(ctx.moves) == 0  # 深度 dz=0 < 1mm 也跳过


def test_roll_correction_then_converge():
    ctx = FakeCtx([m_data(roll=5.0), m_data(roll=0.2), m_data(roll=0.1, dy_mm=2.5)])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is True
    assert len(ctx.moves) == 1
    # 验证运动请求: 绕 tool x 转 +5° (roll_sign=1, TF 单位位姿)
    req = ctx.moves[0]
    assert req.lor == "right" and req.to_frame == "ARM-R-J7_Link"
    qx, qy, qz, qw = _R_to_quat(_rpy_to_R(5.0, 0.0, 0.0))
    p = req.target_pose.pose
    assert abs(p.orientation.x - qx) < 1e-6
    assert abs(p.orientation.z - qz) < 1e-6
    assert abs(p.orientation.w - qw) < 1e-6
    assert abs(p.position.x) < 1e-9 and abs(p.position.y) < 1e-9


def test_y_correction():
    # 阶段1 收敛; 阶段2 dy_mm=10, 扣 cam_y_offset=2 -> dy_eff=8 -> 修 8mm 后收敛
    ctx = FakeCtx([m_data(roll=0.1),
                   m_data(roll=0.1, dy_mm=10.0),
                   m_data(roll=0.1, dy_mm=2.5)])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is True
    assert len(ctx.moves) == 1
    p = ctx.moves[0].target_pose.pose
    assert abs(p.position.y - 0.008) < 1e-9  # +8mm 沿 tool y
    assert abs(p.position.x) < 1e-9


def test_roll_drift_in_y_phase():
    # 阶段2 首次测量 roll 漂移到 4° -> 先转正再测 y
    ctx = FakeCtx([m_data(roll=0.1),
                   m_data(roll=4.0, dy_mm=10.0),   # roll 漂移
                   m_data(roll=0.1, dy_mm=2.5)])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is True
    assert len(ctx.moves) == 1  # 只有 roll 转正那一步
    p = ctx.moves[0].target_pose.pose
    assert abs(p.position.y) < 1e-9  # 是 roll 修正不是 y 修正


def test_depth_feed():
    # 阶段2 收敛 (depth=0.52): dz = (0.52-0.50)*1000 + 0 = 20mm < 容差 30mm -> 进给
    ctx = FakeCtx([m_data(roll=0.1), m_data(roll=0.1, dy_mm=2.5, depth=0.52)])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is True
    assert len(ctx.moves) == 1
    p = ctx.moves[0].target_pose.pose
    assert abs(p.position.x - 0.020) < 1e-9  # z_sign=1 沿 tool x +20mm


def test_depth_out_of_tolerance_rejects():
    # dz = 50mm > 容差 30mm -> 拒动失败
    ctx = FakeCtx([m_data(roll=0.1), m_data(roll=0.1, dy_mm=2.5, depth=0.55)])
    with pytest.raises(FineTuneError, match="拒绝"):
        fine_tune_grasp(ctx, ref_depth=0.50)
    assert len(ctx.moves) == 0


def test_max_iter_not_converged_warns_but_succeeds():
    # y 永不收敛 -> 3 次修正后警告返回, converged=False; 阶段3 再进给一次
    ctx = FakeCtx([m_data(roll=0.1)]
                  + [m_data(roll=0.1, dy_mm=10.0)] * 3)
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is False
    assert r["iterations"] == {"roll": 1, "y": 3}
    assert len(ctx.moves) == 3  # 3 次 y 修正


def test_measure_failure_raises():
    class FailCtx(FakeCtx):
        def ros_call(self, service, params, timeout=None):
            return {"success": False, "message": "YOLO 未检测到取样杆", "data": {}}
    with pytest.raises(FineTuneError, match="YOLO 未检测到"):
        fine_tune_grasp(FailCtx([]), ref_depth=0.50)


def test_cancel_midway():
    ctx = FakeCtx([m_data(roll=5.0)] * 10)
    ctx.cancelled = True
    with pytest.raises(MixedCancelled):
        fine_tune_grasp(ctx, ref_depth=0.50)


def test_dry_run_no_move():
    ctx = FakeCtx([m_data(roll=5.0, dy_mm=10.0, depth=0.52)])
    r = fine_tune_grasp(ctx, ref_depth=0.50, dry_run=True)
    assert len(ctx.moves) == 0
    assert abs(r["planned"]["droll_deg"] - 5.0) < 1e-9
    assert abs(r["planned"]["dy_mm"] - 8.0) < 1e-9
    assert abs(r["planned"]["dz_mm"] - 20.0) < 1e-9


def test_ref_depth_required():
    with pytest.raises(FineTuneError, match="ref_depth"):
        fine_tune_grasp(FakeCtx([]))
```

- [ ] **Step 2: 运行确认失败**

```bash
source /home/jetson/Desktop/furance_robot/ros2_ws/install/setup.bash && cd /home/jetson/Desktop/furance_robot/ros2_ws/src/mixed_execution && python3 -m pytest test/test_fine_tune_grasp.py -v
```
Expected: FAIL — `ModuleNotFoundError`/`ImportError`（模块不存在）

- [ ] **Step 3: 实现 `functions/fine_tune_grasp.py`**

```python
"""取样杆三阶段闭环微调 (工作流 mixed 功能)。

前提: 臂已通过 QR 标定移动到预抓取位 (本功能不做 QR 定位, 不做闭爪)。
流程与 test_fine_tune_grasp.py 一致, 基础设施换成 mixed ctx:
  测量   ctx.ros_call("/camera/fine_tune_measure")   (相机管理节点, 不直连相机)
  运动   ctx.ros_call_typed("/move_pose", MoveP)     (tool 系增量经 T_base_ee@T_offset)
  停稳   ctx.tf_lookup 轮询 (move_pose 返回成功不代表已停稳)
  阶段3 深度进给使用阶段2 最后一次测量的 depth_med (与脚本一致)。

深度/y 修正沿 tool 系固定轴 (x=进刀方向, y=横向), 方向由 camera_config.yaml
的 fine_tune 符号配置决定 (随测量结果返回), 不做参数化。
"""
import logging
import math
import time

import numpy as np

from ..registry import mixed_function

logger = logging.getLogger("mixed_execution.functions.fine_tune_grasp")

EE_LINK = {"left": "ARM-L-J7_Link", "right": "ARM-R-J7_Link"}
MOVE_TIMEOUT = 60.0        # move_pose 服务超时 (秒)
MEASURE_TIMEOUT = 30.0     # 测量服务超时 (秒, 含 settle ~2s)
MAX_ROLL_STEP_DEG = 10.0   # 单次迭代 roll 修正限幅 (度)
MAX_Y_STEP_MM = 50.0       # 单次迭代 y 修正限幅 (mm)
SETTLE_FRAMES = 15         # 每次取帧前丢弃的帧数
SETTLE_SEC = 0.6           # 每次取帧前额外等待 (秒)
STILL_TOL_M = 0.001        # 停稳判定位置容差
STILL_SEC = 0.4            # 停稳判定持续时长


class FineTuneError(Exception):
    """微调失败 (测量失败 / 运动失败 / 深度超容差拒动 / 参数缺失)。"""


# ---- 位姿数学 (与 workflow 上肢 tool 偏移同一约定) ----

def _rpy_to_R(r_deg: float, p_deg: float, y_deg: float) -> np.ndarray:
    r, p, y = math.radians(r_deg), math.radians(p_deg), math.radians(y_deg)
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def _R_to_quat(R: np.ndarray) -> tuple[float, float, float, float]:
    tr = np.trace(R)
    if tr > 0:
        S = math.sqrt(tr + 1.0) * 2
        qw = 0.25 * S
        qx = (R[2, 1] - R[1, 2]) / S
        qy = (R[0, 2] - R[2, 0]) / S
        qz = (R[1, 0] - R[0, 1]) / S
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        S = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        qw = (R[2, 1] - R[1, 2]) / S
        qx = 0.25 * S
        qy = (R[0, 1] + R[1, 0]) / S
        qz = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        qw = (R[0, 2] - R[2, 0]) / S
        qx = (R[0, 1] + R[1, 0]) / S
        qy = 0.25 * S
        qz = (R[1, 2] + R[2, 1]) / S
    else:
        S = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        qw = (R[1, 0] - R[0, 1]) / S
        qx = (R[0, 2] + R[2, 0]) / S
        qy = (R[1, 2] + R[2, 1]) / S
        qz = 0.25 * S
    q = np.array([qx, qy, qz, qw])
    q /= np.linalg.norm(q)
    return float(q[0]), float(q[1]), float(q[2]), float(q[3])


def _T_from_tq(t: np.ndarray, q) -> np.ndarray:
    qx, qy, qz, qw = q
    R = np.array([
        [1 - 2 * qy * qy - 2 * qz * qz, 2 * qx * qy - 2 * qz * qw, 2 * qx * qz + 2 * qy * qw],
        [2 * qx * qy + 2 * qz * qw, 1 - 2 * qx * qx - 2 * qz * qz, 2 * qy * qz - 2 * qx * qw],
        [2 * qx * qz - 2 * qy * qw, 2 * qy * qz + 2 * qx * qw, 1 - 2 * qx * qx - 2 * qy * qy],
    ])
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def _tool_offset_T(droll_deg: float, t_tool_m: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = _rpy_to_R(droll_deg, 0.0, 0.0)  # RPY roll = 绕 tool x
    T[:3, 3] = t_tool_m
    return T


# ---- 基础设施封装 (ctx) ----

def _get_T_base_ee(ctx, ee_link: str) -> np.ndarray:
    res = ctx.tf_lookup("base_link", ee_link)
    if res is None:
        raise FineTuneError(f"无法获取 TF base_link->{ee_link}")
    return _T_from_tq(res[0], res[1])


def _move_p(ctx, arm: str, ee_link: str, T_base_target: np.ndarray) -> None:
    from control_interfaces.srv import MoveP
    from geometry_msgs.msg import PoseStamped
    req = MoveP.Request()
    req.lor = arm
    req.to_frame = ee_link
    req.reference_frame = "base_link"
    req.planner = "ompl"
    pose = PoseStamped()
    pose.header.frame_id = "base_link"
    t = T_base_target[:3, 3]
    qx, qy, qz, qw = _R_to_quat(T_base_target[:3, :3])
    pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = \
        float(t[0]), float(t[1]), float(t[2])
    pose.pose.orientation.x, pose.pose.orientation.y = float(qx), float(qy)
    pose.pose.orientation.z, pose.pose.orientation.w = float(qz), float(qw)
    req.target_pose = pose
    resp = ctx.ros_call_typed("/move_pose", MoveP, req, timeout=MOVE_TIMEOUT)
    if resp is None:
        raise FineTuneError("move_pose 服务调用失败/超时")
    if not getattr(resp, "success", False):
        raise FineTuneError(f"move_pose 失败: {getattr(resp, 'message', '')}")


def _wait_stationary(ctx, ee_link: str, timeout: float = 5.0) -> bool:
    """轮询 TF 直到 EE 位置连续 STILL_SEC 秒变化 < STILL_TOL_M。超时返回 False。"""
    last = None
    stable_since = None
    t0 = time.time()
    while time.time() - t0 < timeout:
        ctx.check_cancel()
        res = ctx.tf_lookup("base_link", ee_link, timeout=0.2)
        if res is None:
            stable_since = None
            continue
        p = res[0]
        if last is not None and np.linalg.norm(p - last) < STILL_TOL_M:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= STILL_SEC:
                return True
        else:
            stable_since = None
        last = p
        time.sleep(0.05)
    return False


# ---- 混合功能 ----

@mixed_function(
    name="fine_tune_grasp",
    description="取样杆三阶段闭环微调 (roll对齐→y对齐→深度进给), "
                "前提: 臂已在预抓取位; 不做 QR 定位和闭爪",
    params_schema=[
        {"name": "camera", "type": "string",
         "description": "相机 ID (right_arm/left_arm)",
         "default": "right_arm", "required": False},
        {"name": "arm", "type": "select", "description": "手臂",
         "options": ["left", "right"], "default": "right", "required": False},
        {"name": "ref_depth", "type": "number",
         "description": "参考深度 (米), 与预抓取位姿绑定, 手动标定",
         "default": None, "required": True},
        {"name": "max_iter", "type": "number", "description": "每阶段闭环迭代上限",
         "default": 3, "required": False},
        {"name": "roll_tol", "type": "number", "description": "roll 收敛阈值 (度)",
         "default": 1.0, "required": False},
        {"name": "y_tol", "type": "number", "description": "y 收敛阈值 (mm)",
         "default": 2.0, "required": False},
        {"name": "depth_tol", "type": "number",
         "description": "深度增量容差 (米), 超出拒动",
         "default": 0.030, "required": False},
        {"name": "dry_run", "type": "bool",
         "description": "只测量并计算拟修正量, 不动臂",
         "default": False, "required": False},
    ],
    moves_base=False,
)
def fine_tune_grasp(ctx, camera: str = "right_arm", arm: str = "right",
                    ref_depth: float = None, max_iter: int = 3,
                    roll_tol: float = 1.0, y_tol: float = 2.0,
                    depth_tol: float = 0.030, dry_run: bool = False):
    """取样杆三阶段闭环微调。"""
    if ref_depth is None:
        raise FineTuneError("参数 ref_depth 必填 (参考深度, 米, 与预抓取位绑定)")
    if arm not in EE_LINK:
        raise FineTuneError(f"未知手臂: {arm} (可选 {list(EE_LINK)})")
    ee_link = EE_LINK[arm]
    viz_paths: list[str] = []
    iters = {"roll": 0, "y": 0}

    def measure_once() -> dict:
        r = ctx.ros_call("/camera/fine_tune_measure",
                         {"camera_id": camera, "settle_frames": SETTLE_FRAMES,
                          "settle_sec": SETTLE_SEC},
                         timeout=MEASURE_TIMEOUT)
        if not r.get("success"):
            raise FineTuneError(f"测量失败: {r.get('message', '')}")
        d = r["data"]
        if d.get("viz_path"):
            viz_paths.append(d["viz_path"])
        return d

    def move_tool(droll_deg: float, t_tool_m: np.ndarray) -> None:
        T_base_ee = _get_T_base_ee(ctx, ee_link)
        _move_p(ctx, arm, ee_link, T_base_ee @ _tool_offset_T(droll_deg, t_tool_m))
        if not _wait_stationary(ctx, ee_link):
            logger.warning("等待臂静止超时, 画面可能是运动中间状态")

    # ---- dry-run: 单帧测量, 只算不动 ----
    if dry_run:
        d = measure_once()
        ft = d["fine_tune"]
        dy_eff = d["dy_mm"] - ft["cam_y_offset_mm"]
        dz_mm = (d["depth_med"] - ref_depth) * 1000.0 + ft["depth_offset_mm"]
        planned = {
            "droll_deg": float(np.clip(ft["roll_sign"] * d["roll_err_deg"],
                                       -MAX_ROLL_STEP_DEG, MAX_ROLL_STEP_DEG)),
            "dy_mm": float(np.clip(ft["y_sign"] * dy_eff,
                                   -MAX_Y_STEP_MM, MAX_Y_STEP_MM)),
            "dz_mm": ft["z_sign"] * dz_mm,
            "depth_out_of_tolerance": bool(abs(dz_mm) > depth_tol * 1000.0),
        }
        ctx.set_progress(100.0, "dry-run 完成")
        return {"converged": True, "iterations": {"roll": 1, "y": 0},
                "planned": planned, "viz_paths": viz_paths}

    # ---- 阶段1: roll 对齐 (先转正再测 y, 避免倾斜时 dy 被杠杆臂污染) ----
    roll_converged = False
    for it in range(1, max_iter + 1):
        ctx.check_cancel()
        iters["roll"] = it
        d = measure_once()
        ctx.set_progress(10.0 * it, f"阶段1 roll迭代{it}: roll={d['roll_err_deg']:+.2f}°")
        if abs(d["roll_err_deg"]) < roll_tol:
            roll_converged = True
            break
        droll = float(np.clip(d["fine_tune"]["roll_sign"] * d["roll_err_deg"],
                              -MAX_ROLL_STEP_DEG, MAX_ROLL_STEP_DEG))
        move_tool(droll, np.zeros(3))
    if not roll_converged:
        logger.warning("阶段1 达到最大迭代 %d, roll 未完全收敛", max_iter)

    # ---- 阶段2: y 对齐 (扣除镜头横向偏移; roll 漂移则先转正) ----
    y_converged = False
    m = d
    for it in range(1, max_iter + 1):
        ctx.check_cancel()
        iters["y"] = it
        d = measure_once()
        m = d
        ft = d["fine_tune"]
        dy_eff = d["dy_mm"] - ft["cam_y_offset_mm"]
        ctx.set_progress(40.0 + 10.0 * it,
                         f"阶段2 y迭代{it}: dy有效={dy_eff:+.1f}mm")
        roll_ok = abs(d["roll_err_deg"]) < roll_tol
        if roll_ok and abs(dy_eff) < y_tol:
            y_converged = True
            break
        if not roll_ok:
            droll = float(np.clip(ft["roll_sign"] * d["roll_err_deg"],
                                  -MAX_ROLL_STEP_DEG, MAX_ROLL_STEP_DEG))
            move_tool(droll, np.zeros(3))
            continue
        dy = float(np.clip(ft["y_sign"] * dy_eff, -MAX_Y_STEP_MM, MAX_Y_STEP_MM))
        t_tool = np.zeros(3)
        t_tool[1] += dy / 1000.0  # tool y
        move_tool(0.0, t_tool)
    if not y_converged:
        logger.warning("阶段2 达到最大迭代 %d, y 未完全收敛", max_iter)

    # ---- 阶段3: 深度进给 (用阶段2 最后一次测量, 一次执行) ----
    ft = m["fine_tune"]
    dz_mm = (m["depth_med"] - ref_depth) * 1000.0 + ft["depth_offset_mm"]
    ctx.set_progress(85.0, f"阶段3 深度: dz={dz_mm:+.1f}mm")
    if abs(dz_mm) > depth_tol * 1000.0:
        raise FineTuneError(
            f"深度增量 {dz_mm:+.1f}mm 超出容差 ±{depth_tol * 1000:.0f}mm, "
            f"拒绝进给 (测量={m['depth_med'] * 1000:.0f}mm "
            f"参考={ref_depth * 1000:.0f}mm 偏移={ft['depth_offset_mm']:+.1f}mm)")
    if abs(dz_mm) >= 1.0:
        t_tool = np.zeros(3)
        t_tool[0] += ft["z_sign"] * dz_mm / 1000.0  # tool x = 进刀方向
        move_tool(0.0, t_tool)

    converged = roll_converged and y_converged
    ctx.set_progress(100.0, "微调完成" + ("" if converged else " (未完全收敛)"))
    return {
        "converged": converged,
        "iterations": iters,
        "final": {
            "roll_err_deg": m["roll_err_deg"],
            "dy_eff_mm": m["dy_mm"] - ft["cam_y_offset_mm"],
            "dz_mm": dz_mm,
        },
        "viz_paths": viz_paths,
    }
```

注意 `test_max_iter_not_converged_warns_but_succeeds` 的场景：阶段2 三次 `dy_mm=10` → 三次 y 修正（每次 +8mm），`m` 为第三次测量；阶段3 `depth=0.50=ref_depth` → dz=0 跳过。moves==3 ✓。

- [ ] **Step 4: 注册功能**

`functions/__init__.py` 末尾加：

```python
from . import fine_tune_grasp  # noqa: F401
```

- [ ] **Step 5: 运行测试确认通过**

```bash
source /home/jetson/Desktop/furance_robot/ros2_ws/install/setup.bash && cd /home/jetson/Desktop/furance_robot/ros2_ws/src/mixed_execution && python3 -m pytest test/test_fine_tune_grasp.py -v
```
Expected: 11 passed

- [ ] **Step 6: 构建 + 注册验证**

```bash
cd /home/jetson/Desktop/furance_robot/ros2_ws && colcon build --packages-select mixed_execution && source install/setup.bash && python3 -c "
from mixed_execution import registry
names = [f['name'] for f in registry.list_functions()]
assert 'fine_tune_grasp' in names, names
print('registered:', names)
"
```
Expected: `registered: [..., 'fine_tune_grasp', ...]`

- [ ] **Step 7: Commit**

```bash
cd /home/jetson/Desktop/furance_robot && git add ros2_ws/src/mixed_execution/ && git commit -m "feat: fine_tune_grasp 混合功能闭环微调"
```

---

### Task 7: 工作流接入 + 真机分阶段验证

把 mixed 步骤插入 `抓取测试.json`，然后真机分四阶段验证。**此任务需要用户在场配合真机操作**（臂/相机在线），执行前先与用户确认时机。

**Files:**
- Modify: `robot_control/backend/data/workflows/robot_001/抓取测试.json`

**Interfaces:**
- Consumes: Task 6 的 `fine_tune_grasp`；`MixedStepConfig`（function/params/timeout/moves_base，引擎已支持）

- [ ] **Step 1: 插入 mixed 步骤**

在 `抓取测试.json` 的 `steps` 数组中，`step_6`（upper_limb moveJ 到位）之后、`step_7`（gripper close）之前插入：

```json
{
 "id": "step_6b",
 "type": "mixed",
 "label": "取样杆微调",
 "config": {
  "function": "fine_tune_grasp",
  "params": {
   "camera": "right_arm",
   "arm": "right",
   "ref_depth": 0.35
  },
  "timeout": 300,
  "moves_base": false
 }
}
```

**`ref_depth` 必须替换为用户用测试脚本在该预抓取位标定过的真实参考深度值（米）**——向用户要这个值再填。改完用 `python3 -m json.tool` 验证 JSON 合法。

- [ ] **Step 2: 构建 + 重启节点（与用户确认后）**

```bash
cd /home/jetson/Desktop/furance_robot/ros2_ws && colcon build --packages-select python_pkgs mixed_execution
```
按现有方式重启 camera_manager 和 mixed_executor 节点（后台服务/launch 由用户操作或按其指示）。

- [ ] **Step 3: 阶段1 — 单独验证测量服务**

相机对准取样杆，臂停在预抓取位：

```bash
source /home/jetson/Desktop/furance_robot/ros2_ws/install/setup.bash
ros2 service call /camera/fine_tune_measure furance_interfaces/srv/GenericCommand "{command: 'fine_tune_measure', params_json: '{\"camera_id\": \"right_arm\", \"settle_frames\": 15, \"settle_sec\": 0.6}'}"
```

Expected: `success=True`，`roll_err_deg`/`dy_mm`/`depth_med` 与此前 `test_fine_tune_grasp.py --dry-run` 在同一姿态下的输出一致（数量级一致）。核对 `fine_tune` 字段与 `camera_config.yaml` 一致。可视化图用 `ls -la <viz_path>` 确认存在（**不要用 Read 读图**），把路径告诉用户自行查看。

- [ ] **Step 4: 阶段2 — mixed 功能 dry_run**

```bash
ros2 service call /mixed/execute furance_interfaces/srv/GenericCommand "{command: 'execute', params_json: '{\"function\": \"fine_tune_grasp\", \"params\": {\"camera\": \"right_arm\", \"arm\": \"right\", \"ref_depth\": <真实参考深度>, \"dry_run\": true}}'}"
# 用返回的 execution_id 轮询
ros2 service call /mixed/status furance_interfaces/srv/GenericCommand "{command: 'status', params_json: '{\"execution_id\": \"<id>\"}'}"
```

Expected: state=succeeded，result 含 `planned`（droll/dy/dz 与测试脚本 dry-run 一致），臂未动。

- [ ] **Step 5: 阶段3 — 全闭环**

去掉 `dry_run` 重新执行。Expected: 臂依次完成 roll/y 修正和深度进给，state=succeeded，`result.converged=True`。若 `converged=False` 查看日志的警告。

- [ ] **Step 6: 阶段4 — 完整工作流**

通过 robot_control 后端启动 `抓取测试` 工作流执行，观察 mixed 步骤状态推送与后续 gripper 闭爪衔接。

- [ ] **Step 7: Commit**

```bash
cd /home/jetson/Desktop/furance_robot && git add "robot_control/backend/data/workflows/robot_001/抓取测试.json" && git commit -m "chore: 抓取测试工作流接入取样杆微调步骤"
```

---

## 验证清单（执行完成后自查）

- [ ] `python3 -m pytest python_pkgs/orbbec_vision/tests/test_fine_tune_measure.py -v` 全过（Task 1）
- [ ] `test_fine_tune_grasp.py --help` 正常（Task 2）
- [ ] 两个 ROS 包 colcon build 成功（Task 4/5/6）
- [ ] mixed_execution mock 测试全过 + `/mixed/list` 含 fine_tune_grasp（Task 6）
- [ ] 真机四阶段验证完成（Task 7，需用户在场）

# 相机视觉模块改进 — 设计文档

## 概述

对控制系统相机模块进行全面改进，涵盖：IR红外流推送、TF标定发布、二维码检测与标定、场景管理、工作流相机编排、上肢坐标偏移。

## 架构

```
前端 (Vue3)
├─ CameraView.vue         + IR视频类型 / 标定面板
└─ WorkflowEditor.vue     + 相机模块(相机/功能/场景) / 坐标偏移(下拉+两排xyzrpy)
        │ REST/WS                    │ REST
后端 (FastAPI)
├─ camera.py              + /calibrate, /scene, /compute_pose
└─ camera_client.py       + calibrate(), scene_op(), compute_target_pose()
        │ ROS2 Service
camera_manager_node (ROS2)
├─ CameraManager          采集 COLOR + DEPTH + IR, WS推流+IR帧
├─ TF Publisher           读取config发布 camera→ee 静态变换
├─ qr_detector.py         二维码检测(彩色+红外), 导入调用
├─ qr_calibrator.py       现场标定(T_qr_workspace)
├─ scene_manager.py        场景yaml CRUD
└─ vision_model.py         视觉模型(预留接口)
```

**集成模式**：混合模式。camera_manager_node 通过 Python import 直接调用功能模块，同时暴露 ROS2 Service 供控制系统后端调用。

## 文件变更清单

### 新增 (均在 `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/`)

| 文件 | 说明 |
|------|------|
| `qr_detector.py` | 二维码检测(彩色BGR + 红外灰度) |
| `qr_calibrator.py` | 现场标定(T_qr_workspace 计算) |
| `scene_manager.py` | 场景 yaml CRUD |
| `vision_model.py` | 视觉模型(预留接口) |
| `scenes/` | 场景 yaml 存储目录 |

### 参考文件 (保留不动，提取核心逻辑)

| 文件 | 说明 |
|------|------|
| `vision/QR_dete.py` | 参考其 `my_estimatePoseSingleMarkers` 和 `ArucoDetector.detectMarkers` 逻辑 |
| `vision/QR_publisher.py` | 参考其 `drawFrameAxes` 和 `cv2.Rodrigues` 坐标轴绘制逻辑 |

### 新增 (ROS2 接口定义)

| 文件 | 说明 |
|------|------|
| `control_interfaces/srv/QRCalibrate.srv` | 标定请求/响应 |
| `control_interfaces/srv/SceneOperation.srv` | 场景 CRUD |
| `control_interfaces/srv/ComputePose.srv` | 工作流目标位姿计算 |

### 改造

| 文件 | 说明 |
|------|------|
| `orbbec_vision/camera_manager_node.py` | +IR采集 +TF发布 +功能模块导入 +新service |
| `robot_control/backend/app/api/camera.py` | +calibrate +scene +compute_pose 端点 |
| `robot_control/backend/app/ros2/camera_client.py` | +calibrate_qr() +scene_operation() +compute_target_pose() |
| `robot_control/frontend/src/views/CameraView.vue` | +标定面板 |
| `robot_control/frontend/src/views/WorkflowEditor.vue` | +相机模块改造 +坐标偏移 |
| `robot_control/frontend/src/api/camera.js` | +新 API |

---

## 模块1: camera_manager_node 改造

### 1.1 IR 帧采集

- `CameraInfo` 增加 `ir_width`, `ir_height`, `ir_fps` 字段
- `_init_cameras()` 增加 IR sensor profile 检测
- `start_stream()` 同时启用 COLOR + DEPTH + IR 三路流
- `_capture_loop()` 中增加 IR 帧获取：
  ```python
  ir_frame = frames.get_ir_frame()
  if ir_frame is None:
      ir_frame = frames.get_left_ir_frame()
  if ir_frame is not None:
      self._ir_frames[camera_id] = self._to_ir_gray(ir_frame)
  ```
- 新增 `_to_ir_gray()` 静态方法，处理 Y8/Y16/Y10/MJPG → uint8 灰度（复用 `test_ir_chessboard.py` 已验证逻辑）
- 新增 `get_latest_ir(camera_id) -> np.ndarray`

### 1.2 WS 推流增加 IR 和 Annotated

- `stream_type` 新增支持：
  - `"ir"` — IR 灰度帧 → JPEG base64 → WS 推送
  - `"annotated"` — QR 检测标注帧（调用 QRDetector 检测并绘制坐标轴） → JPEG base64 → WS 推送
- 前端 CameraView.vue 中 `annotated` 选项移除 `disabled`

### 1.3 TF 发布

- `_publish_calibration_tf()` 在 `_init_cameras()` 末尾调用
- 读取 `camera_config.yaml` 中每个相机的 `calibration.camera_to_<ee_link>` 字段
- 使用 `tf2_ros.TransformBroadcaster` 定时发布静态变换

### 1.4 功能模块导入

```python
from python_pkgs.orbbec_vision.qr_detector import QRDetector
from python_pkgs.orbbec_vision.qr_calibrator import QRCalibrator
from python_pkgs.orbbec_vision.scene_manager import SceneManager
```

### 1.5 新增 ROS2 Service

| Service | 功能 |
|---------|------|
| `/camera/calibrate` | 现场标定 |
| `/camera/scene` | 场景管理(action: list/get/add_point/delete_point/update_point) |
| `/camera/compute_pose` | 工作流目标位姿计算 |

---

## 模块2: qr_detector.py — 二维码检测

### 核心类 QRDetector

```python
class QRDetector:
    def __init__(self, camera_intrinsics: dict, distortion: list):
        # 从 camera_config.yaml calibration.color_intrinsics 读取
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_100)
        self.detector = cv2.aruco.ArucoDetector(self.aruco_dict)
        self.camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
        self.dist_coeffs = np.array(distortion)

    def detect(self, image: np.ndarray, marker_size: float) -> list[QRResult]:
        """
        image: BGR彩色图 或 灰度图(红外)
        marker_size: 二维码物理边长(米)
        返回: [{qr_id, tvec, rvec, corners}, ...]
        """
```

### 检测流程

1. 多通道图像 → 转灰度
2. `detector.detectMarkers(gray)` 检测 ArUco DICT_4X4_100
3. 对每个 marker，`cv2.solvePnP` 求解 rvec/tvec
4. 返回 `QRResult` 列表

### 可视化

- `draw_results(image, results)` — 绘制检测框 + `cv2.drawFrameAxes` 坐标轴
- 返回 BGR 图像，用于前端 "annotated" 推流类型

### 日志

- 独立 logger: `logging.getLogger("orbbec_vision.qr_detector")`
- 每次检测记录：时间戳、相机ID、检测到的 QR ID 列表、每个 QR 的 T_camera_qr

---

## 模块3: qr_calibrator.py — 现场标定

### 核心类 QRCalibrator

```python
class QRCalibrator:
    def __init__(self, tf_buffer: tf2_ros.Buffer, scene_manager: SceneManager,
                 camera_configs: dict):
        ...

    def calibrate(self, camera_id: str, arm: str, qr_id: int,
                  marker_size: float, point_name: str, scene_id: str,
                  color_frame: np.ndarray | None = None,
                  ir_frame: np.ndarray | None = None) -> dict:
```

### 标定流程

1. 从相机获取最新帧（优先彩色，彩色不可用则用红外）→ `QRDetector.detect()` → 得到 `T_camera_qr`
2. 从 TF 获取当前末端位姿 `T_base_ee`（arm 决定 link 名称）
3. 从 config 读取 `T_camera_ee`（相机到末端的标定结果）
4. 计算 `T_ee_qr = T_camera_ee⁻¹ * T_camera_qr`
5. 末端此时对准工作位置，所以 `T_qr_workspace = T_ee_qr⁻¹`
6. 调用 `SceneManager.add_point()` 存入场景 yaml
7. 返回 `{success, T_qr_workspace, message}`

### 日志

- 独立 logger: `logging.getLogger("orbbec_vision.qr_calibrator")`
- 记录完整计算链：各步骤矩阵值，方便调试

---

## 模块4: scene_manager.py — 场景管理

### 存储

- 目录：`orbbec_vision/scenes/`
- 文件：`<scene_id>.yaml`

### yaml 结构

```yaml
scene_id: place_point
description: 放置点
qr_transforms:
  - qr_id: 0
    name: 主放置位
    arm: right
    marker_size: 0.058
    T_qr_workspace:
      translation: [0.35, -0.12, 0.20]
      rotation: [0.0, 0.0, 0.0, 1.0]
vision_models: []
```

### SceneManager 类

```python
class SceneManager:
    def __init__(self, scenes_dir: str): ...

    def list_scenes(self) -> list[dict]:
        """返回所有场景摘要 [{scene_id, description, qr_count, model_count}]"""

    def get_scene(self, scene_id: str) -> dict | None:
        """返回场景完整数据"""

    def save_scene(self, scene_id: str, data: dict) -> bool:
        """创建/覆盖场景"""

    def add_point(self, scene_id: str, qr_id: int, name: str, arm: str,
                  marker_size: float, T_qr_workspace: dict) -> bool

    def delete_point(self, scene_id: str, point_name: str) -> bool

    def update_point(self, scene_id: str, point_name: str, **kwargs) -> bool

    def delete_scene(self, scene_id: str) -> bool
```

### ROS2 Service: `/camera/scene`

统一 service，通过 `action` 参数区分：
- `list` → 返回所有场景
- `get` → 返回单个场景详情
- `create` → 新建场景
- `delete` → 删除场景
- `add_point` → 添加标定点
- `delete_point` → 删除标定点
- `update_point` → 更新标定点

---

## 模块5: vision_model.py — 视觉模型(预留)

```python
class VisionModelBase:
    """视觉模型基类，预留接口"""
    def detect(self, image: np.ndarray) -> list[dict]:
        raise NotImplementedError
    def draw_results(self, image: np.ndarray, results: list[dict]) -> np.ndarray:
        raise NotImplementedError
```

---

## 模块6: ROS2 接口定义

### control_interfaces/srv/QRCalibrate.srv

```
string camera_id
string arm          # left / right
int32 qr_id
float32 marker_size
string point_name
string scene_id
---
bool success
string message
float32[3] translation
float32[4] rotation
```

### control_interfaces/srv/SceneOperation.srv

```
string action        # list / get / create / delete / add_point / delete_point / update_point
string scene_id
string params_json   # JSON: {point_name, qr_id, arm, marker_size, T_qr_workspace, ...}
---
bool success
string message
string result_json   # JSON: 场景数据
```

### control_interfaces/srv/ComputePose.srv

```
string camera_id
string function      # qr_detect / vision_model
string scene_id
string point_name
---
bool success
string message
float64 x
float64 y
float64 z
float64 roll
float64 pitch
float64 yaw
```

---

## 模块7: 后端 API

### 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/robot/{id}/camera/calibrate` | 现场标定 |
| POST | `/api/v1/robot/{id}/camera/scene` | 场景管理 |
| POST | `/api/v1/robot/{id}/camera/compute_pose` | 工作流目标位姿计算 |

### camera_client.py 新增方法

```python
async def calibrate_qr(self, camera_id, arm, qr_id, marker_size,
                       point_name, scene_id) -> dict
async def scene_operation(self, action, scene_id=None, params=None) -> dict
async def compute_target_pose(self, camera_id, function, scene_id,
                              point_name) -> dict
```

---

## 模块8: 前端 — 相机页面 (CameraView.vue)

### 新增"现场标定"卡片

在"抓取检测"卡片下方：

- 相机下拉（已连接）
- 手臂下拉（left/right）
- 场景下拉 + 新建场景(名称+描述输入框)
- 标定点名输入框
- QR ID 输入框（默认 0）
- QR 尺寸输入框（单位 m）
- 执行标定按钮
- 结果展示区

### 视频类型下拉增加"红外图"选项

---

## 模块9: 前端 — 工作流相机模块 (WorkflowEditor.vue)

### vision 步骤改造

```
相机:   [下拉: head / left_arm / right_arm]
功能:   [下拉: 二维码 / 视觉模型]
场景:   [下拉: 场景文件列表]
标定点: [下拉: 该场景下的标定点列表]

输出: target_pose — 后续坐标模式用「关联视觉」引用
```

- 选"二维码"→ 场景加载含 `qr_transforms` 的场景，标定点加载对应列表
- 选"视觉模型"→ 预留，场景加载含 `vision_models` 的场景

---

## 模块10: 前端 — 上肢坐标偏移 (WorkflowEditor.vue)

### 坐标模式 UI 改造

```
模式: [下拉: 手动输入 / 当前末端 / 关联视觉]

── 输入位姿 ──
x: [____] y: [____] z: [____]
roll: [____] pitch: [____] yaw: [____]
(模式2显示代称: 「当前末端姿态」)
(模式3显示代称: 「视觉输出 — <步骤label>」)

── 偏移 ──
☑ 启用偏移
参考系: [☐ base_link] [☐ tool_link] (tool_link 根据 arm 自动判断)
dx: [____] dy: [____] dz: [____]
droll: [____] dpitch: [____] dyaw: [____]
```

### 三种模式

| 模式 | 第一排来源 | 编辑时显示 | 执行时解析 |
|------|-----------|-----------|-----------|
| 手动输入 | 用户填写 | 空白输入框 | 直接使用 |
| 当前末端 | 执行时获取 TF | 代称文字 | `base_link → ARM-{L/R}-J7_Link` |
| 关联视觉 | 前序 vision 步骤输出 | 代称文字 | 对应 vision 步骤 label |

关联视觉下拉选项：当前步骤之前所有 vision 步骤的 `label`（步骤名称），不是 step id。

### 偏移计算

- base_link: 输入位姿 + base_link 坐标系下的 xyzrpy 偏移
- tool_link: `T_final = T_input * T_offset`（偏移在末端坐标系下做）

---

## 日志规范

每个功能模块使用独立 logger：

| 模块 | logger 名称 |
|------|------------|
| 二维码检测 | `orbbec_vision.qr_detector` |
| 现场标定 | `orbbec_vision.qr_calibrator` |
| 场景管理 | `orbbec_vision.scene_manager` |
| 视觉模型 | `orbbec_vision.vision_model` |

日志内容：时间戳、输入参数、中间计算结果、最终输出，确保后续调试可追溯。

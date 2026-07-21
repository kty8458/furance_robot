# Camera Vision Improvement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement QR code detection, scene management, on-site calibration, workflow vision module, and upper-limb coordinate offset for the robot camera system.

**Architecture:** Hybrid mode — camera_manager_node imports vision modules directly in-process while exposing ROS2 Services for the backend. New modules go under `orbbec_vision/`. Three new ROS2 srv files, three new backend API endpoints, and frontend UI changes in CameraView and WorkflowEditor.

**Tech Stack:** Python 3.10, ROS2 Humble, OpenCV (ArUco), NumPy, SciPy, Vue 3 + Element Plus, FastAPI

## Global Constraints

- All new Python files go under `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/`
- New srv files go under `ros2_ws/src/t1_robot/control_interfaces/srv/`
- Follow existing service patterns: use `GenericCommand` from `furance_interfaces` for simple services, custom srv for structured ones
- Loggers use `logging.getLogger("orbbec_vision.<module>")` format
- Python 3.10+ type hints
- ruff linter, pytest + pytest-asyncio for tests

---

### Task 1: ROS2 Service Definitions (3 new srv files)

**Files:**
- Create: `ros2_ws/src/t1_robot/control_interfaces/srv/QRCalibrate.srv`
- Create: `ros2_ws/src/t1_robot/control_interfaces/srv/SceneOperation.srv`
- Create: `ros2_ws/src/t1_robot/control_interfaces/srv/ComputePose.srv`

**Interfaces:**
- Produces: `QRCalibrate`, `SceneOperation`, `ComputePose` srv types for Tasks 6, 8, 9

- [ ] **Step 1: Create QRCalibrate.srv**

Write `ros2_ws/src/t1_robot/control_interfaces/srv/QRCalibrate.srv`:
```
string camera_id
string arm
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

- [ ] **Step 2: Create SceneOperation.srv**

Write `ros2_ws/src/t1_robot/control_interfaces/srv/SceneOperation.srv`:
```
string action
string scene_id
string params_json
---
bool success
string message
string result_json
```

- [ ] **Step 3: Create ComputePose.srv**

Write `ros2_ws/src/t1_robot/control_interfaces/srv/ComputePose.srv`:
```
string camera_id
string function
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

- [ ] **Step 4: Build ROS2 interfaces**

```bash
cd ~/Desktop/furance_robot/ros2_ws && colcon build --packages-select control_interfaces
```

- [ ] **Step 5: Commit**

```bash
git add ros2_ws/src/t1_robot/control_interfaces/srv/QRCalibrate.srv ros2_ws/src/t1_robot/control_interfaces/srv/SceneOperation.srv ros2_ws/src/t1_robot/control_interfaces/srv/ComputePose.srv
git commit -m "feat: add QRCalibrate, SceneOperation, ComputePose srv definitions"
```

---

### Task 2: Scene Manager (scene_manager.py)

**Files:**
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/scene_manager.py`
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/scenes/` (empty directory, first save creates it)

**Interfaces:**
- Produces: `SceneManager` class consumed by Task 5 (qr_calibrator) and Task 6 (camera_manager_node)

- [ ] **Step 1: Write scene_manager.py**

Write `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/scene_manager.py`:

```python
"""场景管理器 — 场景 yaml 文件 CRUD 操作。"""

import logging
import os
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("orbbec_vision.scene_manager")

DEFAULT_SCENE_TEMPLATE = {
    "scene_id": "",
    "description": "",
    "qr_transforms": [],
    "vision_models": [],
}


class SceneManager:
    """管理场景 yaml 文件，每个场景一个 <scene_id>.yaml 文件。"""

    def __init__(self, scenes_dir: str):
        self._dir = Path(scenes_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        logger.info("SceneManager initialized, scenes_dir=%s", self._dir)

    # ---- 内部 ----

    def _path(self, scene_id: str) -> Path:
        return self._dir / f"{scene_id}.yaml"

    def _load(self, scene_id: str) -> Optional[dict]:
        p = self._path(scene_id)
        if not p.exists():
            return None
        with open(p) as f:
            return yaml.safe_load(f) or {}

    def _save(self, scene_id: str, data: dict):
        data["scene_id"] = scene_id
        with open(self._path(scene_id), "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
        logger.info("Scene saved: %s", scene_id)

    # ---- 公共 API ----

    def list_scenes(self) -> list[dict]:
        """返回所有场景摘要列表。"""
        result = []
        for p in sorted(self._dir.glob("*.yaml")):
            sid = p.stem
            try:
                data = self._load(sid)
                if data:
                    result.append({
                        "scene_id": sid,
                        "description": data.get("description", ""),
                        "qr_count": len(data.get("qr_transforms", [])),
                        "model_count": len(data.get("vision_models", [])),
                    })
            except Exception:
                logger.exception("Failed to read scene: %s", sid)
        logger.info("list_scenes: %d scenes found", len(result))
        return result

    def get_scene(self, scene_id: str) -> Optional[dict]:
        """返回场景完整数据。"""
        data = self._load(scene_id)
        if data is None:
            logger.warning("get_scene: %s not found", scene_id)
        else:
            logger.info("get_scene: %s loaded, qr=%d, models=%d",
                        scene_id, len(data.get("qr_transforms", [])),
                        len(data.get("vision_models", [])))
        return data

    def create_scene(self, scene_id: str, description: str = "") -> bool:
        """新建场景。"""
        if self._path(scene_id).exists():
            logger.warning("create_scene: %s already exists", scene_id)
            return False
        data = dict(DEFAULT_SCENE_TEMPLATE)
        data["scene_id"] = scene_id
        data["description"] = description
        self._save(scene_id, data)
        logger.info("create_scene: %s created", scene_id)
        return True

    def delete_scene(self, scene_id: str) -> bool:
        """删除场景文件。"""
        p = self._path(scene_id)
        if not p.exists():
            logger.warning("delete_scene: %s not found", scene_id)
            return False
        p.unlink()
        logger.info("delete_scene: %s deleted", scene_id)
        return True

    def add_point(self, scene_id: str, qr_id: int, name: str, arm: str,
                  marker_size: float, T_qr_workspace: dict) -> bool:
        """添加标定点到场景。"""
        data = self._load(scene_id)
        if data is None:
            logger.warning("add_point: scene %s not found", scene_id)
            return False
        # 删除同名点
        data.setdefault("qr_transforms", [])
        data["qr_transforms"] = [p for p in data["qr_transforms"] if p.get("name") != name]
        data["qr_transforms"].append({
            "qr_id": qr_id,
            "name": name,
            "arm": arm,
            "marker_size": marker_size,
            "T_qr_workspace": T_qr_workspace,
        })
        self._save(scene_id, data)
        logger.info("add_point: scene=%s point=%s qr_id=%d arm=%s T=%s",
                    scene_id, name, qr_id, arm, T_qr_workspace)
        return True

    def delete_point(self, scene_id: str, point_name: str) -> bool:
        """从场景删除标定点。"""
        data = self._load(scene_id)
        if data is None:
            return False
        before = len(data.get("qr_transforms", []))
        data["qr_transforms"] = [p for p in data.get("qr_transforms", [])
                                 if p.get("name") != point_name]
        if len(data["qr_transforms"]) == before:
            logger.warning("delete_point: point %s not found in %s", point_name, scene_id)
            return False
        self._save(scene_id, data)
        logger.info("delete_point: scene=%s point=%s deleted", scene_id, point_name)
        return True

    def update_point(self, scene_id: str, point_name: str, **kwargs) -> bool:
        """更新标定点字段。"""
        data = self._load(scene_id)
        if data is None:
            return False
        for p in data.get("qr_transforms", []):
            if p.get("name") == point_name:
                for k, v in kwargs.items():
                    p[k] = v
                self._save(scene_id, data)
                logger.info("update_point: scene=%s point=%s updated %s",
                            scene_id, point_name, list(kwargs.keys()))
                return True
        logger.warning("update_point: point %s not found in %s", point_name, scene_id)
        return False

    def find_point(self, scene_id: str, point_name: str) -> Optional[dict]:
        """查找标定点。"""
        data = self._load(scene_id)
        if data is None:
            return None
        for p in data.get("qr_transforms", []):
            if p.get("name") == point_name:
                return p
        return None
```

- [ ] **Step 2: Verify scenes/ directory creation**

```bash
ls -la ~/Desktop/furance_robot/ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/scenes/
```

- [ ] **Step 3: Commit**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/scene_manager.py
git commit -m "feat: add scene_manager.py with yaml-based scene CRUD"
```

---

### Task 3: Vision Model Placeholder (vision_model.py)

**Files:**
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/vision_model.py`

**Interfaces:**
- Produces: `VisionModelBase` class, consumed by Task 6 for future vision model support

- [ ] **Step 1: Write vision_model.py**

Write `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/vision_model.py`:

```python
"""视觉模型基类 — 预留接口，后续扩展 YOLO 等模型。"""

import logging
import numpy as np

logger = logging.getLogger("orbbec_vision.vision_model")


class VisionModelBase:
    """视觉模型基类，所有视觉模型需继承此类。"""

    def detect(self, image: np.ndarray) -> list[dict]:
        """
        检测图像中的目标。
        Args:
            image: BGR 彩色图 (H, W, 3) 或灰度图 (H, W)
        Returns:
            [{label, confidence, bbox: [x1,y1,x2,y2], pose: {x,y,z,roll,pitch,yaw}}, ...]
        """
        raise NotImplementedError

    def draw_results(self, image: np.ndarray, results: list[dict]) -> np.ndarray:
        """
        在图像上绘制检测结果。
        Args:
            image: BGR 彩色图
            results: detect() 的返回值
        Returns:
            标注后的 BGR 图像
        """
        raise NotImplementedError


# 模型注册表，方便后续动态加载
MODEL_REGISTRY: dict[str, type] = {}
```

- [ ] **Step 2: Commit**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/vision_model.py
git commit -m "feat: add vision_model.py placeholder base class"
```

---

### Task 4: QR Detector (qr_detector.py)

**Files:**
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/qr_detector.py`

**References:** Extract logic from `vision/QR_dete.py` (detectMarkers, my_estimatePoseSingleMarkers) and `vision/QR_publisher.py` (drawFrameAxes)

**Interfaces:**
- Produces: `QRDetector` class, consumed by Task 5 (qr_calibrator) and Task 6 (camera_manager_node for annotated stream)

- [ ] **Step 1: Write qr_detector.py**

Write `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/qr_detector.py`:

```python
"""二维码检测模块 — 支持彩色 (BGR) 和红外 (灰度) 图像。

参考 vision/QR_dete.py 的 detectMarkers + my_estimatePoseSingleMarkers 逻辑，
以及 vision/QR_publisher.py 的 drawFrameAxes 可视化。
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import cv2.aruco as aruco
import numpy as np

logger = logging.getLogger("orbbec_vision.qr_detector")


@dataclass
class QRResult:
    qr_id: int
    tvec: np.ndarray       # (3,1) 平移向量，单位米
    rvec: np.ndarray       # (3,1) 旋转向量
    corners: np.ndarray    # (1,4,2) 角点


class QRDetector:
    """ArUco 二维码检测器。

    使用 DICT_4X4_100 字典，cv2.aruco.ArucoDetector 检测，
    cv2.SOLVEPNP_IPPE_SQUARE 求解位姿。
    """

    def __init__(self, camera_matrix: np.ndarray, dist_coeffs: np.ndarray):
        """
        Args:
            camera_matrix: (3,3) 相机内参矩阵
            dist_coeffs: (5,) 或 (N,) 畸变系数
        """
        self.camera_matrix = np.array(camera_matrix, dtype=np.float64)
        self.dist_coeffs = np.array(dist_coeffs, dtype=np.float64)
        self.aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_100)
        self.detector = aruco.ArucoDetector(self.aruco_dict)
        logger.info("QRDetector initialized: fx=%.2f fy=%.2f cx=%.2f cy=%.2f",
                    self.camera_matrix[0, 0], self.camera_matrix[1, 1],
                    self.camera_matrix[0, 2], self.camera_matrix[1, 2])

    def detect(self, image: np.ndarray, marker_size: float) -> list[QRResult]:
        """
        检测图像中的所有 ArUco 标记并估计位姿。

        Args:
            image: BGR 彩色图 (H,W,3) 或 灰度图 (H,W) — 自动转灰度
            marker_size: 二维码物理边长，单位 米

        Returns:
            QRResult 列表，按 qr_id 排序
        """
        t0 = time.time()

        # 转灰度
        if image.ndim == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif image.ndim == 3 and image.shape[2] == 1:
            gray = image[:, :, 0]
        else:
            gray = image

        # 检测
        corners, ids, _ = self.detector.detectMarkers(gray)

        results: list[QRResult] = []
        if ids is None or len(ids) == 0:
            elapsed = (time.time() - t0) * 1000
            logger.debug("detect: no markers found (%.1fms)", elapsed)
            return results

        # 自定义姿态估计 (SOLVEPNP_IPPE_SQUARE, 参考 QR_dete.py)
        marker_points = np.array([
            [-marker_size / 2, marker_size / 2, 0],
            [marker_size / 2, marker_size / 2, 0],
            [marker_size / 2, -marker_size / 2, 0],
            [-marker_size / 2, -marker_size / 2, 0],
        ], dtype=np.float32)

        for i, c in enumerate(corners):
            _, rvec, tvec = cv2.solvePnP(
                marker_points, c, self.camera_matrix, self.dist_coeffs,
                flags=cv2.SOLVEPNP_IPPE_SQUARE,
            )
            results.append(QRResult(
                qr_id=int(ids[i][0]),
                tvec=np.array(tvec, dtype=np.float64),
                rvec=np.array(rvec, dtype=np.float64),
                corners=c,
            ))

        results.sort(key=lambda r: r.qr_id)
        elapsed = (time.time() - t0) * 1000
        ids_str = [r.qr_id for r in results]
        logger.info("detect: found %d markers, ids=%s (%.1fms)", len(results), ids_str, elapsed)
        for r in results:
            logger.info("  QR id=%d tvec=[%.4f, %.4f, %.4f] rvec=[%.4f, %.4f, %.4f]",
                        r.qr_id,
                        float(r.tvec[0]), float(r.tvec[1]), float(r.tvec[2]),
                        float(r.rvec[0]), float(r.rvec[1]), float(r.rvec[2]))

        return results

    def draw_results(self, image: np.ndarray, results: list[QRResult],
                     axis_length: float = 0.05) -> np.ndarray:
        """
        在图像上绘制检测框和坐标轴。

        Args:
            image: BGR 彩色图 (H,W,3) 或 灰度图 (H,W)
            results: detect() 的返回值
            axis_length: 坐标轴长度 (米)

        Returns:
            BGR 标注图像
        """
        if image.ndim == 2:
            out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            out = image.copy()

        corners_list = [r.corners for r in results]
        ids_list = np.array([[r.qr_id] for r in results], dtype=np.int32)

        if corners_list:
            aruco.drawDetectedMarkers(out, corners_list, ids_list)

        for r in results:
            cv2.drawFrameAxes(out, self.camera_matrix, self.dist_coeffs,
                             r.rvec, r.tvec, axis_length)

        # 叠加文字信息
        for i, r in enumerate(results):
            pos = (int(r.corners[0, 0, 0]), int(r.corners[0, 0, 1]) - 10)
            if pos[1] < 15:
                pos = (pos[0], 15)
            text = f"ID:{r.qr_id} t=[{float(r.tvec[0]):.3f},{float(r.tvec[1]):.3f},{float(r.tvec[2]):.3f}]"
            cv2.putText(out, text, pos, cv2.FONT_HERSHEY_SIMPLEX,
                       0.4, (0, 255, 255), 1)

        return out
```

- [ ] **Step 2: Commit**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/qr_detector.py
git commit -m "feat: add qr_detector.py — ArUco detection with pose estimation"
```

---

### Task 5: QR Calibrator (qr_calibrator.py)

**Files:**
- Create: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/qr_calibrator.py`

**Interfaces:**
- Consumes: `QRDetector` (Task 4), `SceneManager` (Task 2)
- Produces: `QRCalibrator` class, consumed by Task 6 (camera_manager_node service handler)

- [ ] **Step 1: Write qr_calibrator.py**

Write `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/qr_calibrator.py`:

```python
"""现场标定模块 — 计算 QR 码到工作位置的固定变换 T_qr_workspace。

流程:
  1. QRDetector 检测 QR → T_camera_qr
  2. TF 获取当前末端位姿 T_base_ee
  3. config 读取 T_camera_ee (相机到末端)
  4. T_ee_qr = inv(T_camera_ee) * T_camera_qr
  5. T_qr_workspace = inv(T_ee_qr)  (末端对准工作位置)
  6. SceneManager.add_point() 存储
"""

import logging
import time
from typing import Optional

import numpy as np

from python_pkgs.orbbec_vision.qr_detector import QRDetector
from python_pkgs.orbbec_vision.scene_manager import SceneManager

logger = logging.getLogger("orbbec_vision.qr_calibrator")

# arm → ee_link 映射
ARM_EE_LINKS = {
    "left": "ARM-L-J7_Link",
    "right": "ARM-R-J7_Link",
}


def _rodrigues_to_matrix(rvec: np.ndarray) -> np.ndarray:
    """旋转向量 → 3x3 旋转矩阵。"""
    R, _ = cv2.Rodrigues(rvec)
    return R


def _make_transform(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    """3x3 R + (3,) t → 4x4 齐次变换矩阵。"""
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t.ravel()
    return T


def _matrix_to_pose(T: np.ndarray) -> tuple[list[float], list[float]]:
    """4x4 → (translation [x,y,z], rotation [x,y,z,w])。"""
    t = T[:3, 3].tolist()
    R = T[:3, :3]
    tr = np.trace(R)
    if tr > 0:
        S = np.sqrt(tr + 1.0) * 2
        qw = 0.25 * S
        qx = (R[2, 1] - R[1, 2]) / S
        qy = (R[0, 2] - R[2, 0]) / S
        qz = (R[1, 0] - R[0, 1]) / S
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        S = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        qw = (R[2, 1] - R[1, 2]) / S
        qx = 0.25 * S
        qy = (R[0, 1] + R[1, 0]) / S
        qz = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        qw = (R[0, 2] - R[2, 0]) / S
        qx = (R[0, 1] + R[1, 0]) / S
        qy = 0.25 * S
        qz = (R[1, 2] + R[2, 1]) / S
    else:
        S = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        qw = (R[1, 0] - R[0, 1]) / S
        qx = (R[0, 2] + R[2, 0]) / S
        qy = (R[1, 2] + R[2, 1]) / S
        qz = 0.25 * S
    quat = [float(qx), float(qy), float(qz), float(qw)]
    norm = np.sqrt(sum(v * v for v in quat))
    return t, [v / norm for v in quat]


class QRCalibrator:
    """QR 现场标定器。"""

    def __init__(self, scene_manager: SceneManager, camera_configs: dict):
        """
        Args:
            scene_manager: SceneManager 实例
            camera_configs: {camera_id: config_dict} 从 camera_config.yaml 解析
        """
        self._scene = scene_manager
        self._camera_configs = camera_configs
        self._detectors: dict[str, QRDetector] = {}
        self._init_detectors()

    def _init_detectors(self):
        """为每个有标定内参的相机创建 QRDetector。"""
        for cid, cfg in self._camera_configs.items():
            calib = cfg.get("calibration", {})
            intrinsics = calib.get("color_intrinsics", {})
            if intrinsics.get("fx"):
                K = np.array([
                    [intrinsics["fx"], 0, intrinsics["cx"]],
                    [0, intrinsics["fy"], intrinsics["cy"]],
                    [0, 0, 1],
                ], dtype=np.float64)
                D = np.array(intrinsics.get("distortion", [0, 0, 0, 0, 0]), dtype=np.float64)
                self._detectors[cid] = QRDetector(K, D)
                logger.info("QRCalibrator: detector ready for camera '%s'", cid)

    def calibrate(self, camera_id: str, arm: str, qr_id: int,
                  marker_size: float, point_name: str, scene_id: str,
                  color_frame: Optional[np.ndarray] = None,
                  ir_frame: Optional[np.ndarray] = None,
                  T_base_ee: Optional[np.ndarray] = None) -> dict:
        """
        执行现场标定。

        Args:
            camera_id: 相机 ID
            arm: "left" / "right"
            qr_id: 目标 QR 码 ID
            marker_size: QR 码物理边长 (米)
            point_name: 标定点名称
            scene_id: 场景 ID
            color_frame: 彩色帧 (BGR)，可选
            ir_frame: 红外帧 (灰度)，可选
            T_base_ee: base_link → end-effector 的 4x4 变换，可选

        Returns:
            {success, message, translation, rotation, T_qr_workspace}
        """
        t0 = time.time()
        logger.info("calibrate: camera=%s arm=%s qr_id=%d marker_size=%.4f point=%s scene=%s",
                    camera_id, arm, qr_id, marker_size, point_name, scene_id)

        # 1. QR 检测 → T_camera_qr
        detector = self._detectors.get(camera_id)
        if detector is None:
            return {"success": False, "message": f"No intrinsics for camera: {camera_id}"}

        frame = color_frame if color_frame is not None else ir_frame
        if frame is None:
            return {"success": False, "message": "No frame available"}

        results = detector.detect(frame, marker_size)
        qr_result = next((r for r in results if r.qr_id == qr_id), None)
        if qr_result is None:
            return {"success": False, "message": f"QR id={qr_id} not found in frame, detected: {[r.qr_id for r in results]}"}

        R_cam_qr = _rodrigues_to_matrix(qr_result.rvec)
        T_camera_qr = _make_transform(R_cam_qr, qr_result.tvec)
        logger.info("calibrate: T_camera_qr=\n%s", T_camera_qr)

        # 2. 获取 T_camera_ee
        cfg = self._camera_configs.get(camera_id, {})
        calib = cfg.get("calibration", {})
        ee_link = ARM_EE_LINKS.get(arm, f"ARM-{arm.upper()}-J7_Link")
        cam_to_ee_key = f"camera_to_{ee_link}"
        cam_to_ee = calib.get(cam_to_ee_key, {})
        if not cam_to_ee.get("translation"):
            return {"success": False, "message": f"No camera_to_ee calibration for {camera_id} → {ee_link}"}

        rot = cam_to_ee["rotation"]
        trans = cam_to_ee["translation"]
        # rotation in config is stored as rodrigues-like [rx, ry, rz]
        R_cam_ee, _ = cv2.Rodrigues(np.array(rot, dtype=np.float64))
        T_camera_ee = _make_transform(R_cam_ee, np.array(trans, dtype=np.float64))
        logger.info("calibrate: T_camera_ee (from config)=\n%s", T_camera_ee)

        # 3. T_ee_qr = inv(T_camera_ee) * T_camera_qr
        T_ee_qr = np.linalg.inv(T_camera_ee) @ T_camera_qr
        logger.info("calibrate: T_ee_qr = inv(T_camera_ee) * T_camera_qr =\n%s", T_ee_qr)

        # 4. T_qr_workspace = inv(T_ee_qr) (末端对准工作位置)
        T_qr_workspace = np.linalg.inv(T_ee_qr)
        logger.info("calibrate: T_qr_workspace = inv(T_ee_qr) =\n%s", T_qr_workspace)

        # 5. 存储
        translation, rotation = _matrix_to_pose(T_qr_workspace)
        ok = self._scene.add_point(
            scene_id=scene_id,
            qr_id=qr_id,
            name=point_name,
            arm=arm,
            marker_size=marker_size,
            T_qr_workspace={"translation": translation, "rotation": rotation},
        )
        if not ok:
            return {"success": False, "message": f"Failed to save point to scene {scene_id}"}

        elapsed = (time.time() - t0) * 1000
        logger.info("calibrate: done (%.1fms) T_qr_workspace trans=%s rot=%s",
                    elapsed, translation, rotation)
        return {
            "success": True,
            "message": "Calibration complete",
            "translation": translation,
            "rotation": rotation,
        }
```

Note: This file needs `import cv2` at the top for `cv2.Rodrigues`. Add after the `import numpy as np` line:

```python
import cv2
```

- [ ] **Step 2: Commit**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/qr_calibrator.py
git commit -m "feat: add qr_calibrator.py — on-site QR-to-workspace calibration"
```

---

### Task 6: camera_manager_node.py Modifications

**Files:**
- Modify: `ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_manager_node.py`

**Interfaces:**
- Consumes: `QRDetector` (Task 4), `QRCalibrator` (Task 5), `SceneManager` (Task 2)
- Produces: New services `/camera/calibrate`, `/camera/scene`, `/camera/compute_pose`; IR frames via WS; TF broadcast

This task modifies the existing `camera_manager_node.py` in multiple places. Each sub-step targets a specific section.

- [ ] **Step 1: Add IR fields to CameraInfo**

In the `CameraInfo` dataclass (after `depth_fps`), add:

```python
ir_width: int = 0
ir_height: int = 0
ir_fps: int = 0
```

In `to_dict()`, add after `depth_fps`:

```python
"ir_width": self.ir_width, "ir_height": self.ir_height,
"ir_fps": self.ir_fps,
```

- [ ] **Step 2: Add IR storage to CameraManager.__init__**

Add after `self._depth_frames` line:

```python
self._ir_frames: dict[str, Optional[np.ndarray]] = {}
```

And in `_init_cameras()` loop, add after `self._depth_frames[cid] = None`:

```python
self._ir_frames[cid] = None
```

- [ ] **Step 3: Detect IR sensor profile in _init_cameras()**

After the depth profile detection block (the `except Exception: pass` for depth), add:

```python
try:
    ir_profiles = pipeline.get_stream_profile_list(OBSensorType.IR_SENSOR)
    ir_profile = ir_profiles.get_default_video_stream_profile()
    info.ir_width, info.ir_height, info.ir_fps = ir_profile.get_width(), ir_profile.get_height(), ir_profile.get_fps()
except Exception:
    try:
        ir_profiles = pipeline.get_stream_profile_list(OBSensorType.LEFT_IR_SENSOR)
        ir_profile = ir_profiles.get_default_video_stream_profile()
        info.ir_width, info.ir_height, info.ir_fps = ir_profile.get_width(), ir_profile.get_height(), ir_profile.get_fps()
    except Exception:
        pass
```

- [ ] **Step 4: Enable IR stream in start_stream()**

In `start_stream()`, after the depth stream enable block, add:

```python
try:
    config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.IR_SENSOR).get_default_video_stream_profile())
except OBError:
    try:
        config.enable_stream(pipeline.get_stream_profile_list(OBSensorType.LEFT_IR_SENSOR).get_default_video_stream_profile())
    except OBError:
        pass
```

- [ ] **Step 5: Add IR frame capture in _capture_loop()**

In `_capture_loop()`, after the depth frame capture block, add:

```python
irf = frames.get_ir_frame()
if irf is None:
    irf = frames.get_left_ir_frame() if hasattr(frames, "get_left_ir_frame") else None
if irf is not None:
    self._ir_frames[camera_id] = self._to_ir_gray(irf)
```

- [ ] **Step 6: Add _to_ir_gray() static method to CameraManager**

Add after `_to_depth_mm()`:

```python
@staticmethod
def _to_ir_gray(frame) -> Optional[np.ndarray]:
    """IR 帧 → uint8 灰度图 (复用 test_ir_chessboard.py 已验证逻辑)。"""
    from pyorbbecsdk import OBFormat
    w, h, fmt = frame.get_width(), frame.get_height(), frame.get_format()
    raw = np.frombuffer(frame.get_data(), dtype=np.uint8)

    if fmt == OBFormat.Y8:
        return raw.reshape((h, w)).copy()
    elif fmt in (OBFormat.Y16, OBFormat.YUYV, OBFormat.YUY2):
        raw_u16 = raw.view(np.uint16).reshape((h, w))
        try:
            bit_size = frame.pixel_available_bit_size()
        except Exception:
            bit_size = 16
        scale = 1.0 / (2 ** (bit_size - 8)) if bit_size > 8 else 1.0
        return (raw_u16.astype(np.float32) * scale).clip(0, 255).astype(np.uint8)
    elif fmt == OBFormat.MJPG:
        return cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
    return None
```

- [ ] **Step 7: Add get_latest_ir() method to CameraManager**

Add after `get_latest_depth()`:

```python
def get_latest_ir(self, camera_id: str) -> Optional[np.ndarray]:
    with self._lock:
        f = self._ir_frames.get(camera_id)
        return f.copy() if f is not None else None
```

- [ ] **Step 8: Add IR and annotated stream types to WS push_loop()**

In `_WsProtocol.handle()`'s `push_loop()`, replace the `if stream_type == "depth":` block with:

```python
if stream_type == "depth":
    frame = self._manager.get_latest_depth(camera_id)
    if frame is not None:
        frame = _render_depth_3d(frame)
elif stream_type == "ir":
    frame = self._manager.get_latest_ir(camera_id)
elif stream_type == "annotated":
    frame = self._manager.get_latest_color(camera_id)
    if frame is not None and hasattr(self._manager, '_qr_detector'):
        try:
            results = self._manager._qr_detector.detect(frame, 0.058)
            frame = self._manager._qr_detector.draw_results(frame, results)
        except Exception:
            logger.exception("annotated frame generation failed")
else:
    frame = self._manager.get_latest_color(camera_id)
```

- [ ] **Step 9: Add module imports and initialization in main()**

In the `main()` function, after `manager = CameraManager(config_path)`, add:

```python
# ---- Vision modules ----
import yaml as _yaml
_config_dir = os.path.dirname(config_path)
_scenes_dir = os.path.join(_config_dir, "scenes")
_scene_manager = None
_qr_calibrator = None

# 加载相机配置供 QRCalibrator 使用
with open(config_path) as _f:
    _cam_configs = {c["id"]: c for c in _yaml.safe_load(_f).get("cameras", [])}

try:
    from python_pkgs.orbbec_vision.scene_manager import SceneManager
    _scene_manager = SceneManager(_scenes_dir)
    logger.info("SceneManager initialized")
except Exception:
    logger.exception("Failed to init SceneManager")

try:
    from python_pkgs.orbbec_vision.qr_calibrator import QRCalibrator
    _qr_calibrator = QRCalibrator(_scene_manager, _cam_configs)
    logger.info("QRCalibrator initialized")
except Exception:
    logger.exception("Failed to init QRCalibrator")

# QRDetector for annotated stream (lazy per camera)
_qr_detectors: dict[str, object] = {}
```

- [ ] **Step 10: Add TF broadcaster in main()**

After the module initialization block, add:

```python
# ---- TF Broadcaster for camera→ee transforms ----
import tf2_ros
_tf_broadcaster = tf2_ros.TransformBroadcaster(node)
_tf_timer = None

def _publish_calibration_tfs():
    """读取 config 中的 camera_to_<ee_link> 并发布静态 TF。"""
    for cid, cfg in _cam_configs.items():
        calib = cfg.get("calibration", {})
        for key, transform in calib.items():
            if not key.startswith("camera_to_"):
                continue
            ee_link = key[len("camera_to_"):]
            t = transform.get("translation", [0, 0, 0])
            r = transform.get("rotation", [0, 0, 0])
            # rotation is stored as rodrigues vector
            import cv2 as _cv2
            R_mat, _ = _cv2.Rodrigues(np.array(r, dtype=np.float64))
            # matrix → quaternion
            from geometry_msgs.msg import TransformStamped
            _tf_msg = TransformStamped()
            _tf_msg.header.stamp = node.get_clock().now().to_msg()
            _tf_msg.header.frame_id = cid + "_link" if not cid.endswith("_link") else cid
            _tf_msg.child_frame_id = ee_link
            _tf_msg.transform.translation.x = float(t[0]) / 1000.0 if abs(t[0]) > 10 else float(t[0])
            _tf_msg.transform.translation.y = float(t[1]) / 1000.0 if abs(t[1]) > 10 else float(t[1])
            _tf_msg.transform.translation.z = float(t[2]) / 1000.0 if abs(t[2]) > 10 else float(t[2])
            # rotation matrix → quaternion
            tr = np.trace(R_mat)
            if tr > 0:
                S = np.sqrt(tr + 1.0) * 2
                qw = 0.25 * S
                qx = (R_mat[2, 1] - R_mat[1, 2]) / S
                qy = (R_mat[0, 2] - R_mat[2, 0]) / S
                qz = (R_mat[1, 0] - R_mat[0, 1]) / S
            elif R_mat[0, 0] > R_mat[1, 1] and R_mat[0, 0] > R_mat[2, 2]:
                S = np.sqrt(1.0 + R_mat[0, 0] - R_mat[1, 1] - R_mat[2, 2]) * 2
                qw = (R_mat[2, 1] - R_mat[1, 2]) / S
                qx = 0.25 * S
                qy = (R_mat[0, 1] + R_mat[1, 0]) / S
                qz = (R_mat[0, 2] + R_mat[2, 0]) / S
            elif R_mat[1, 1] > R_mat[2, 2]:
                S = np.sqrt(1.0 + R_mat[1, 1] - R_mat[0, 0] - R_mat[2, 2]) * 2
                qw = (R_mat[0, 2] - R_mat[2, 0]) / S
                qx = (R_mat[0, 1] + R_mat[1, 0]) / S
                qy = 0.25 * S
                qz = (R_mat[1, 2] + R_mat[2, 1]) / S
            else:
                S = np.sqrt(1.0 + R_mat[2, 2] - R_mat[0, 0] - R_mat[1, 1]) * 2
                qw = (R_mat[1, 0] - R_mat[0, 1]) / S
                qx = (R_mat[0, 2] + R_mat[2, 0]) / S
                qy = (R_mat[1, 2] + R_mat[2, 1]) / S
                qz = 0.25 * S
            _tf_msg.transform.rotation.x = float(qx)
            _tf_msg.transform.rotation.y = float(qy)
            _tf_msg.transform.rotation.z = float(qz)
            _tf_msg.transform.rotation.w = float(qw)
            _tf_broadcaster.sendTransform(_tf_msg)
            logger.debug("TF: %s → %s published", _tf_msg.header.frame_id, ee_link)

_tf_timer = node.create_timer(1.0, _publish_calibration_tfs)
logger.info("TF broadcaster started for camera→ee transforms")
```

- [ ] **Step 11: Add new ROS2 service handlers in main()**

After the existing `_handle_stream_stop` service, add:

```python
# /camera/calibrate
from control_interfaces.srv import QRCalibrate

def _handle_calibrate(request, response):
    if _qr_calibrator is None:
        response.success = False
        response.message = "QRCalibrator not available"
        return response
    # Get latest frame from the requested camera
    color_frame = manager.get_latest_color(request.camera_id)
    ir_frame = manager.get_latest_ir(request.camera_id)
    result = _qr_calibrator.calibrate(
        camera_id=request.camera_id,
        arm=request.arm,
        qr_id=request.qr_id,
        marker_size=request.marker_size,
        point_name=request.point_name,
        scene_id=request.scene_id,
        color_frame=color_frame,
        ir_frame=ir_frame,
    )
    response.success = result["success"]
    response.message = result["message"]
    if result["success"]:
        response.translation = result["translation"]
        response.rotation = result["rotation"]
    return response

node.create_service(QRCalibrate, "/camera/calibrate", _handle_calibrate)

# /camera/scene
from control_interfaces.srv import SceneOperation

def _handle_scene(request, response):
    if _scene_manager is None:
        response.success = False
        response.message = "SceneManager not available"
        return response
    import json as _json
    params = _json.loads(request.params_json) if request.params_json else {}
    action = request.action
    scene_id = request.scene_id
    try:
        if action == "list":
            result = _scene_manager.list_scenes()
            response.success = True
            response.result_json = _json.dumps(result)
        elif action == "get":
            data = _scene_manager.get_scene(scene_id)
            if data is None:
                response.success = False
                response.message = f"Scene not found: {scene_id}"
            else:
                response.success = True
                response.result_json = _json.dumps(data)
        elif action == "create":
            ok = _scene_manager.create_scene(scene_id, params.get("description", ""))
            response.success = ok
            response.message = "Created" if ok else f"Already exists: {scene_id}"
        elif action == "delete":
            ok = _scene_manager.delete_scene(scene_id)
            response.success = ok
            response.message = "Deleted" if ok else f"Not found: {scene_id}"
        elif action == "add_point":
            ok = _scene_manager.add_point(
                scene_id=scene_id,
                qr_id=params.get("qr_id", 0),
                name=params.get("name", ""),
                arm=params.get("arm", "right"),
                marker_size=params.get("marker_size", 0.058),
                T_qr_workspace=params.get("T_qr_workspace", {}),
            )
            response.success = ok
            response.message = "Point added" if ok else "Failed"
        elif action == "delete_point":
            ok = _scene_manager.delete_point(scene_id, params.get("name", ""))
            response.success = ok
            response.message = "Point deleted" if ok else "Not found"
        elif action == "update_point":
            update_kwargs = {k: v for k, v in params.items() if k != "name"}
            ok = _scene_manager.update_point(scene_id, params.get("name", ""), **update_kwargs)
            response.success = ok
            response.message = "Updated" if ok else "Not found"
        else:
            response.success = False
            response.message = f"Unknown action: {action}"
    except Exception as e:
        logger.exception("Scene operation failed: %s", action)
        response.success = False
        response.message = str(e)
    return response

node.create_service(SceneOperation, "/camera/scene", _handle_scene)

# /camera/compute_pose
from control_interfaces.srv import ComputePose

def _handle_compute_pose(request, response):
    if _scene_manager is None:
        response.success = False
        response.message = "SceneManager not available"
        return response
    try:
        # 1. Get scene point
        point = _scene_manager.find_point(request.scene_id, request.point_name)
        if point is None:
            response.success = False
            response.message = f"Point not found: {request.scene_id}/{request.point_name}"
            return response

        T_qr_ws = point.get("T_qr_workspace", {})
        t_ws = T_qr_ws.get("translation", [0, 0, 0])
        r_ws = T_qr_ws.get("rotation", [0, 0, 0, 1])

        # 2. Get camera intrinsics for QR detection
        cfg = _cam_configs.get(request.camera_id, {})
        calib = cfg.get("calibration", {})
        intrinsics = calib.get("color_intrinsics", {})

        if not intrinsics.get("fx"):
            response.success = False
            response.message = f"No intrinsics for camera: {request.camera_id}"
            return response

        # 3. Detect QR from latest frame
        from python_pkgs.orbbec_vision.qr_detector import QRDetector
        import numpy as np

        K = np.array([
            [intrinsics["fx"], 0, intrinsics["cx"]],
            [0, intrinsics["fy"], intrinsics["cy"]],
            [0, 0, 1],
        ], dtype=np.float64)
        D = np.array(intrinsics.get("distortion", [0, 0, 0, 0, 0]), dtype=np.float64)
        detector = QRDetector(K, D)

        color_frame = manager.get_latest_color(request.camera_id)
        ir_frame = manager.get_latest_ir(request.camera_id)
        frame = color_frame if color_frame is not None else ir_frame
        if frame is None:
            response.success = False
            response.message = "No frame available"
            return response

        marker_size = point.get("marker_size", 0.058)
        qr_id = point.get("qr_id", 0)
        results = detector.detect(frame, marker_size)
        qr_result = next((r for r in results if r.qr_id == qr_id), None)
        if qr_result is None:
            response.success = False
            response.message = f"QR id={qr_id} not found"
            return response

        # 4. T_camera_qr
        import cv2 as _cv2
        R_cam_qr, _ = _cv2.Rodrigues(qr_result.rvec)
        T_cam_qr = np.eye(4)
        T_cam_qr[:3, :3] = R_cam_qr
        T_cam_qr[:3, 3] = qr_result.tvec.ravel()

        # 5. T_qr_workspace from scene
        rot_vec, _ = _cv2.Rodrigues(np.array([r_ws[0], r_ws[1], r_ws[2]], dtype=np.float64))
        # Actually rotation is stored as quaternion [x,y,z,w]
        qx, qy, qz, qw = r_ws
        R_ws = np.array([
            [1 - 2*qy*qy - 2*qz*qz, 2*qx*qy - 2*qz*qw, 2*qx*qz + 2*qy*qw],
            [2*qx*qy + 2*qz*qw, 1 - 2*qx*qx - 2*qz*qz, 2*qy*qz - 2*qx*qw],
            [2*qx*qz - 2*qy*qw, 2*qy*qz + 2*qx*qw, 1 - 2*qx*qx - 2*qy*qy],
        ])
        T_qr_ws = np.eye(4)
        T_qr_ws[:3, :3] = R_ws
        T_qr_ws[:3, 3] = t_ws

        # 6. T_camera_ws = T_camera_qr * T_qr_workspace
        T_cam_ws = T_cam_qr @ T_qr_ws

        # 7. Get T_camera_ee from config
        arm = point.get("arm", "right")
        ee_link = f"ARM-{arm.upper()}-J7_Link"
        cam_to_ee = calib.get(f"camera_to_{ee_link}", {})
        if not cam_to_ee.get("translation"):
            response.success = False
            response.message = f"No camera_to_ee calibration for {ee_link}"
            return response
        R_cam_ee, _ = _cv2.Rodrigues(np.array(cam_to_ee["rotation"], dtype=np.float64))
        T_cam_ee = np.eye(4)
        T_cam_ee[:3, :3] = R_cam_ee
        T_cam_ee[:3, 3] = cam_to_ee["translation"]

        # 8. T_ee_ws = inv(T_camera_ee) * T_camera_ws
        T_ee_ws = np.linalg.inv(T_cam_ee) @ T_cam_ws

        # 9. Extract xyzrpy (rotation matrix → euler xyz)
        x, y, z = float(T_ee_ws[0, 3]), float(T_ee_ws[1, 3]), float(T_ee_ws[2, 3])
        R_ee = T_ee_ws[:3, :3]
        # Pure numpy: rotation matrix → euler angles (xyz convention)
        sy = np.sqrt(R_ee[0, 0] ** 2 + R_ee[1, 0] ** 2)
        singular = sy < 1e-6
        if not singular:
            roll = float(np.arctan2(R_ee[2, 1], R_ee[2, 2]))
            pitch = float(np.arctan2(-R_ee[2, 0], sy))
            yaw = float(np.arctan2(R_ee[1, 0], R_ee[0, 0]))
        else:
            roll = float(np.arctan2(-R_ee[1, 2], R_ee[1, 1]))
            pitch = float(np.arctan2(-R_ee[2, 0], sy))
            yaw = 0.0

        response.success = True
        response.message = "Computed"
        response.x = x
        response.y = y
        response.z = z
        response.roll = roll
        response.pitch = pitch
        response.yaw = yaw

        logger.info("compute_pose: camera=%s scene=%s point=%s → xyz=[%.4f,%.4f,%.4f] rpy=[%.4f,%.4f,%.4f]",
                    request.camera_id, request.scene_id, request.point_name,
                    x, y, z, roll, pitch, yaw)
    except Exception as e:
        logger.exception("compute_pose failed")
        response.success = False
        response.message = str(e)
    return response

node.create_service(ComputePose, "/camera/compute_pose", _handle_compute_pose)
```

- [ ] **Step 12: Rebuild and verify**

```bash
cd ~/Desktop/furance_robot/ros2_ws && colcon build --packages-select python_pkgs
```

- [ ] **Step 13: Commit**

```bash
git add ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_manager_node.py
git commit -m "feat: add IR stream, TF broadcast, calibrate/scene/compute_pose services to camera_manager_node"
```

---

### Task 7: Backend camera_client.py Modifications

**Files:**
- Modify: `robot_control/backend/app/ros2/camera_client.py`

**Interfaces:**
- Consumes: `/camera/calibrate`, `/camera/scene`, `/camera/compute_pose` ROS2 services (Task 6)
- Produces: `calibrate_qr()`, `scene_operation()`, `compute_target_pose()` methods for Task 8

- [ ] **Step 1: Add new methods to RealCameraClient**

After `detect_grasp_pose()`, add:

```python
async def calibrate_qr(self, camera_id: str, arm: str, qr_id: int,
                       marker_size: float, point_name: str,
                       scene_id: str) -> dict[str, Any]:
    """现场标定: 计算 T_qr_workspace 并存入场景。"""
    return await self._call("/camera/calibrate", {
        "camera_id": camera_id,
        "arm": arm,
        "qr_id": qr_id,
        "marker_size": marker_size,
        "point_name": point_name,
        "scene_id": scene_id,
    })

async def scene_operation(self, action: str, scene_id: str = None,
                          params: dict = None) -> dict[str, Any]:
    """场景管理: list / get / create / delete / add_point / delete_point / update_point。"""
    req_params = {
        "action": action,
        "scene_id": scene_id or "",
        "params_json": json.dumps(params) if params else "{}",
    }
    return await self._call("/camera/scene", req_params)

async def compute_target_pose(self, camera_id: str, function: str,
                              scene_id: str, point_name: str) -> dict[str, Any]:
    """工作流目标位姿计算。"""
    return await self._call("/camera/compute_pose", {
        "camera_id": camera_id,
        "function": function,
        "scene_id": scene_id,
        "point_name": point_name,
    })
```

- [ ] **Step 2: Add corresponding mock methods to MockCameraClient**

After the existing `detect_grasp_pose` mock, add:

```python
async def calibrate_qr(self, camera_id: str, arm: str, qr_id: int,
                       marker_size: float, point_name: str,
                       scene_id: str) -> dict[str, Any]:
    return {"success": True, "message": f"mock: calibrated {point_name}",
            "data": {"translation": [0.35, -0.12, 0.20],
                     "rotation": [0.0, 0.0, 0.0, 1.0]}}

async def scene_operation(self, action: str, scene_id: str = None,
                          params: dict = None) -> dict[str, Any]:
    if action == "list":
        return {"success": True, "data": [
            {"scene_id": "place_point", "description": "放置点 (Mock)", "qr_count": 1, "model_count": 0},
        ]}
    return {"success": True, "message": f"mock: scene {action}"}

async def compute_target_pose(self, camera_id: str, function: str,
                              scene_id: str, point_name: str) -> dict[str, Any]:
    return {"success": True, "message": f"mock: computed {point_name}",
            "data": {"x": 350.0, "y": -120.0, "z": 200.0,
                     "roll": 180.0, "pitch": 0.0, "yaw": 90.0}}
```

Also add abstract methods to `CameraClientBase`:

```python
@abstractmethod
async def calibrate_qr(self, camera_id: str, arm: str, qr_id: int,
                       marker_size: float, point_name: str,
                       scene_id: str) -> dict[str, Any]:
    ...

@abstractmethod
async def scene_operation(self, action: str, scene_id: str = None,
                          params: dict = None) -> dict[str, Any]:
    ...

@abstractmethod
async def compute_target_pose(self, camera_id: str, function: str,
                              scene_id: str, point_name: str) -> dict[str, Any]:
    ...
```

- [ ] **Step 3: Commit**

```bash
git add robot_control/backend/app/ros2/camera_client.py
git commit -m "feat: add calibrate_qr, scene_operation, compute_target_pose to camera client"
```

---

### Task 8: Backend camera.py API Modifications

**Files:**
- Modify: `robot_control/backend/app/api/camera.py`

**Interfaces:**
- Consumes: `camera_client.calibrate_qr()`, `scene_operation()`, `compute_target_pose()` (Task 7)
- Produces: REST endpoints for frontend (Tasks 10, 11)

- [ ] **Step 1: Add new endpoints to camera.py**

Append to `robot_control/backend/app/api/camera.py`:

```python
@router.post("/calibrate", response_model=ApiResponse)
async def calibrate_qr(robot_id: str, req: dict, request: Request):
    """现场标定: 计算 QR 到工作位置的变换并存入场景。
    
    Body: {
        camera_id, arm, qr_id, marker_size, point_name, scene_id
    }
    """
    result = await _get_client(request).calibrate_qr(
        camera_id=req.get("camera_id", "head"),
        arm=req.get("arm", "right"),
        qr_id=req.get("qr_id", 0),
        marker_size=req.get("marker_size", 0.058),
        point_name=req.get("point_name", ""),
        scene_id=req.get("scene_id", ""),
    )
    if not result.get("success"):
        return ApiResponse(code=3001, message=result.get("message", "Calibration failed"))
    return ApiResponse(data=result.get("data", result))


@router.post("/scene", response_model=ApiResponse)
async def scene_operation(robot_id: str, req: dict, request: Request):
    """场景管理: action=list|get|create|delete|add_point|delete_point|update_point.
    
    Body: {action, scene_id, params: {...}}
    """
    result = await _get_client(request).scene_operation(
        action=req.get("action", "list"),
        scene_id=req.get("scene_id"),
        params=req.get("params"),
    )
    if not result.get("success"):
        return ApiResponse(code=3001, message=result.get("message", "Scene operation failed"))
    return ApiResponse(data=result.get("data", result))


@router.post("/compute_pose", response_model=ApiResponse)
async def compute_pose(robot_id: str, req: dict, request: Request):
    """工作流目标位姿计算。
    
    Body: {camera_id, function, scene_id, point_name}
    """
    result = await _get_client(request).compute_target_pose(
        camera_id=req.get("camera_id", "head"),
        function=req.get("function", "qr_detect"),
        scene_id=req.get("scene_id", ""),
        point_name=req.get("point_name", ""),
    )
    if not result.get("success"):
        return ApiResponse(code=3001, message=result.get("message", "Compute pose failed"))
    return ApiResponse(data=result.get("data", result))
```

- [ ] **Step 2: Commit**

```bash
git add robot_control/backend/app/api/camera.py
git commit -m "feat: add calibrate, scene, compute_pose REST endpoints"
```

---

### Task 9: Frontend camera.js API Additions

**Files:**
- Modify: `robot_control/frontend/src/api/camera.js`

- [ ] **Step 1: Add new API methods**

Append to the `cameraApi` object:

```javascript
calibrate: (data) =>
  api.post(`/robot/${ROBOT_ID}/camera/calibrate`, data),

scene: (action, sceneId, params = {}) =>
  api.post(`/robot/${ROBOT_ID}/camera/scene`, {
    action,
    scene_id: sceneId || '',
    params,
  }),

computePose: (data) =>
  api.post(`/robot/${ROBOT_ID}/camera/compute_pose`, data),
```

- [ ] **Step 2: Commit**

```bash
git add robot_control/frontend/src/api/camera.js
git commit -m "feat: add calibrate, scene, computePose to camera API"
```

---

### Task 10: Frontend CameraView.vue Modifications

**Files:**
- Modify: `robot_control/frontend/src/views/CameraView.vue`

- [ ] **Step 1: Add "红外图" option to stream type selector**

In the `<el-select v-model="streamType">` block, add:

```html
<el-option label="红外图" value="ir" />
```

Also remove the `:disabled="true"` from the annotated option:

```html
<el-option label="带框标注" value="annotated" />
```

- [ ] **Step 2: Add "现场标定" card after the "抓取检测" card**

Add after the closing `</el-card>` of the grasp detection card:

```html
<el-card class="tech-card">
  <template #header>
    <div class="tech-card-header">
      <el-icon><Connection /></el-icon>
      <span style="margin-left: 8px">现场标定</span>
    </div>
  </template>

  <div style="margin-bottom: 10px">
    <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">相机</div>
    <el-select v-model="calibCameraId" style="width: 100%">
      <el-option v-for="cam in cameras" :key="cam.id"
        :label="`${cam.name} (${cam.id})`" :value="cam.id"
        :disabled="!cam.connected" />
    </el-select>
  </div>

  <div style="margin-bottom: 10px">
    <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">手臂</div>
    <el-select v-model="calibArm" style="width: 100%">
      <el-option label="左臂" value="left" />
      <el-option label="右臂" value="right" />
    </el-select>
  </div>

  <div style="margin-bottom: 10px">
    <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">场景</div>
    <div style="display: flex; gap: 6px">
      <el-select v-model="calibSceneId" style="flex: 1" filterable clearable
        placeholder="选择已有场景" @change="onCalibSceneChange">
        <el-option v-for="s in sceneList" :key="s.scene_id"
          :label="`${s.scene_id} (${s.description})`" :value="s.scene_id" />
      </el-select>
      <el-button size="small" @click="showNewScene = !showNewScene">
        {{ showNewScene ? '取消' : '新建' }}
      </el-button>
    </div>
    <div v-if="showNewScene" style="margin-top: 6px; display: flex; gap: 6px">
      <el-input v-model="newSceneId" placeholder="场景ID" size="small" style="flex: 1" />
      <el-input v-model="newSceneDesc" placeholder="描述" size="small" style="flex: 1" />
      <el-button size="small" type="primary" @click="createScene">创建</el-button>
    </div>
  </div>

  <div style="margin-bottom: 10px">
    <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">标定点名</div>
    <el-input v-model="calibPointName" placeholder="例如: 主放置位" size="small" />
  </div>

  <el-row :gutter="8" style="margin-bottom: 10px">
    <el-col :span="12">
      <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">QR ID</div>
      <el-input-number v-model="calibQrId" :min="0" size="small" controls-position="right" style="width: 100%" />
    </el-col>
    <el-col :span="12">
      <div style="font-size: 12px; color: #9ca3af; margin-bottom: 4px">QR 尺寸 (m)</div>
      <el-input-number v-model="calibMarkerSize" :min="0.01" :step="0.001" :precision="3"
        size="small" controls-position="right" style="width: 100%" />
    </el-col>
  </el-row>

  <el-button size="small" type="success" style="width: 100%" @click="runCalibration" :loading="calibrating">
    执行标定
  </el-button>

  <div v-if="calibResult" class="detect-result" style="margin-top: 10px">
    <div class="detect-title">标定结果 — T_qr_workspace</div>
    <div style="font-size: 11px; color: #9ca3af; margin-bottom: 4px">Translation (m)</div>
    <div style="font-family: 'Consolas', monospace; font-size: 12px; color: #e5e7eb">
      x: {{ calibResult.translation?.[0]?.toFixed(4) ?? '--' }}
      y: {{ calibResult.translation?.[1]?.toFixed(4) ?? '--' }}
      z: {{ calibResult.translation?.[2]?.toFixed(4) ?? '--' }}
    </div>
    <div style="font-size: 11px; color: #9ca3af; margin-bottom: 4px; margin-top: 4px">Rotation (xyzw)</div>
    <div style="font-family: 'Consolas', monospace; font-size: 12px; color: #e5e7eb">
      x: {{ calibResult.rotation?.[0]?.toFixed(4) ?? '--' }}
      y: {{ calibResult.rotation?.[1]?.toFixed(4) ?? '--' }}
      z: {{ calibResult.rotation?.[2]?.toFixed(4) ?? '--' }}
      w: {{ calibResult.rotation?.[3]?.toFixed(4) ?? '--' }}
    </div>
  </div>
</el-card>
```

- [ ] **Step 3: Add script state and methods**

In the `<script setup>` block, add after `const detectResult = ref(null)`:

```javascript
// ---- 标定状态 ----
const calibCameraId = ref('head')
const calibArm = ref('right')
const calibSceneId = ref('')
const calibPointName = ref('')
const calibQrId = ref(0)
const calibMarkerSize = ref(0.058)
const calibrating = ref(false)
const calibResult = ref(null)
const sceneList = ref([])
const showNewScene = ref(false)
const newSceneId = ref('')
const newSceneDesc = ref('')
```

Add new icon import at the top:
```javascript
import { View, Aim, VideoCamera, Connection } from '@element-plus/icons-vue'
```

Add methods:

```javascript
async function loadSceneList() {
  try {
    const res = await cameraApi.scene('list')
    sceneList.value = res.data || []
  } catch { sceneList.value = [] }
}

async function createScene() {
  if (!newSceneId.value) { ElMessage.warning('请输入场景ID'); return }
  try {
    await cameraApi.scene('create', newSceneId.value, { description: newSceneDesc.value })
    ElMessage.success(`场景 ${newSceneId.value} 已创建`)
    calibSceneId.value = newSceneId.value
    showNewScene.value = false
    newSceneId.value = ''
    newSceneDesc.value = ''
    await loadSceneList()
  } catch (e) { ElMessage.error(e.message || '创建失败') }
}

function onCalibSceneChange() { /* placeholder */ }

async function runCalibration() {
  if (!calibSceneId.value) { ElMessage.warning('请选择场景'); return }
  if (!calibPointName.value) { ElMessage.warning('请输入标定点名'); return }
  calibrating.value = true
  calibResult.value = null
  try {
    const res = await cameraApi.calibrate({
      camera_id: calibCameraId.value,
      arm: calibArm.value,
      qr_id: calibQrId.value,
      marker_size: calibMarkerSize.value,
      point_name: calibPointName.value,
      scene_id: calibSceneId.value,
    })
    calibResult.value = res.data || res
    ElMessage.success('标定完成')
  } catch (e) {
    ElMessage.error(e.message || '标定失败')
  } finally {
    calibrating.value = false
  }
}
```

Update `onMounted` / `onDropdownToggle` to also load scene list:
```javascript
async function onDropdownToggle(visible) {
  if (visible) { loadCameras(); loadSceneList() }
}
```

Also add `loadSceneList()` to the existing `onMounted` call (or call within it):
In the `onMounted` block, add `loadSceneList()` after `loadCameras()` if not already there.

- [ ] **Step 4: Commit**

```bash
git add robot_control/frontend/src/views/CameraView.vue
git commit -m "feat: add IR stream type, calibration panel to CameraView"
```

---

### Task 11: Frontend WorkflowEditor.vue — Vision Step Modifications

**Files:**
- Modify: `robot_control/frontend/src/views/WorkflowEditor.vue`

- [ ] **Step 1: Add scene and function state**

Add after `const cameraList = ref([])`:

```javascript
const sceneList = ref([])
const scenePoints = ref({})  // {scene_id: [point names]}
```

- [ ] **Step 2: Add scene loading methods**

Add after `loadCameraList()`:

```javascript
async function loadSceneList() {
  try {
    const { cameraApi } = await import('../api/camera')
    const res = await cameraApi.scene('list')
    sceneList.value = res.data || []
  } catch { sceneList.value = [] }
}

async function loadScenePoints(sceneId) {
  if (!sceneId) { scenePoints.value[sceneId] = []; return }
  if (scenePoints.value[sceneId]) return
  try {
    const { cameraApi } = await import('../api/camera')
    const res = await cameraApi.scene('get', sceneId)
    const data = res.data || {}
    scenePoints.value[sceneId] = (data.qr_transforms || []).map(p => p.name)
  } catch { scenePoints.value[sceneId] = [] }
}
```

Call `loadSceneList()` in `onMounted` after `loadCameraList()`.

- [ ] **Step 3: Modify the vision step template**

Replace the existing vision step template (lines 308-331 in the current file) with:

```html
<!-- vision -->
<template v-if="step.type === 'vision'">
  <el-row :gutter="8" style="margin-bottom: 6px">
    <el-col :span="12">
      <div style="font-size: 11px; color: #6b7b8d">相机</div>
      <el-select v-model="step.config.camera_id" size="small" style="width: 100%">
        <el-option
          v-for="cam in cameraList"
          :key="cam.id"
          :label="`${cam.name} (${cam.id})`"
          :value="cam.id"
          :disabled="!cam.connected"
        />
      </el-select>
    </el-col>
    <el-col :span="12">
      <div style="font-size: 11px; color: #6b7b8d">功能</div>
      <el-select v-model="step.config.function" size="small" style="width: 100%">
        <el-option label="二维码" value="qr_detect" />
        <el-option label="视觉模型" value="vision_model" :disabled="true" />
      </el-select>
    </el-col>
  </el-row>
  <el-row :gutter="8" style="margin-bottom: 6px">
    <el-col :span="12">
      <div style="font-size: 11px; color: #6b7b8d">场景</div>
      <el-select v-model="step.config.scene" size="small" style="width: 100%"
        @change="val => { loadScenePoints(val); step.config.point_name = '' }">
        <el-option v-for="s in sceneList" :key="s.scene_id"
          :label="`${s.scene_id} (${s.description})`" :value="s.scene_id" />
      </el-select>
    </el-col>
    <el-col :span="12">
      <div style="font-size: 11px; color: #6b7b8d">标定点</div>
      <el-select v-model="step.config.point_name" size="small" style="width: 100%">
        <el-option v-for="p in (scenePoints[step.config.scene] || [])"
          :key="p" :label="p" :value="p" />
      </el-select>
    </el-col>
  </el-row>
  <div style="font-size: 10px; color: #6b7b8d; margin-top: 4px">
    输出: target_pose — 后续坐标模式用「关联视觉」引用
  </div>
</template>
```

- [ ] **Step 4: Update defaults**

In `addStep()`, update the vision defaults:
```javascript
vision: { camera_id: cameraList.value.find(c => c.connected)?.id || 'head', function: 'qr_detect', scene: '', point_name: '' },
```

In `selectWorkflow()`, update the vision initialization:
```javascript
if (s.type === 'vision' && !s.config.function) s.config.function = 'qr_detect'
if (s.type === 'vision' && !s.config.scene) s.config.scene = ''
if (s.type === 'vision' && !s.config.point_name) s.config.point_name = ''
```

- [ ] **Step 5: Commit**

```bash
git add robot_control/frontend/src/views/WorkflowEditor.vue
git commit -m "feat: add function/scene/point selectors to vision workflow step"
```

---

### Task 12: Frontend WorkflowEditor.vue — Upper Limb Coordinate Offset

**Files:**
- Modify: `robot_control/frontend/src/views/WorkflowEditor.vue` (same file as Task 11)

- [ ] **Step 1: Replace the pose-mode template for upper_limb step**

Replace the existing `<template v-else>` block (lines 247-263, the coordinate mode section) with:

```html
<template v-else>
  <!-- 坐标模式 -->
  <el-row :gutter="8" style="margin-bottom: 6px">
    <el-col :span="12">
      <div style="font-size: 11px; color: #6b7b8d">模式</div>
      <el-select v-model="step.config.pose_mode" size="small" style="width: 100%"
        @change="val => onPoseModeChange(step, val)">
        <el-option label="手动输入" value="manual" />
        <el-option label="当前末端" value="current_ee" />
        <el-option label="关联视觉" value="vision" />
      </el-select>
    </el-col>
    <el-col :span="12" v-if="step.config.pose_mode === 'vision'">
      <div style="font-size: 11px; color: #6b7b8d">关联视觉步骤</div>
      <el-select v-model="step.config.vision_step_label" size="small" style="width: 100%"
        @change="label => onVisionStepLabelChange(step, label)">
        <el-option v-for="vs in getPrecedingVisionLabels(idx)" :key="vs.label"
          :label="vs.label || vs.id" :value="vs.label" />
      </el-select>
    </el-col>
  </el-row>

  <!-- 输入位姿 -->
  <div style="font-size: 11px; color: #00d4ff; margin-bottom: 4px">── 输入位姿 ──</div>
  <el-row :gutter="6" style="margin-bottom: 8px">
    <el-col :span="4" v-for="(f, fi) in poseFields" :key="'in_'+fi">
      <div style="font-size: 10px; color: #6b7b8d">{{ f }}</div>
      <el-input
        v-if="step.config.pose_mode === 'manual'"
        v-model="step.config.position[f]"
        :placeholder="f"
        size="small"
      />
      <div v-else-if="step.config.pose_mode === 'current_ee'"
        style="font-size: 11px; color: #00ff88; padding-top: 5px; font-style: italic">
        当前末端
      </div>
      <div v-else-if="step.config.pose_mode === 'vision'"
        style="font-size: 11px; color: #ffa500; padding-top: 5px; font-style: italic">
        视觉输出
      </div>
    </el-col>
  </el-row>

  <!-- 偏移 -->
  <div style="margin-bottom: 6px">
    <el-checkbox v-model="step.config.enable_offset" size="small" @change="onOffsetToggle(step)">
      <span style="font-size: 11px; color: #9ca3af">启用偏移</span>
    </el-checkbox>
  </div>
  <template v-if="step.config.enable_offset">
    <div style="font-size: 11px; color: #00d4ff; margin-bottom: 4px">── 偏移 ──</div>
    <div style="margin-bottom: 6px">
      <span style="font-size: 11px; color: #9ca3af; margin-right: 10px">参考系:</span>
      <el-checkbox v-model="step.config.offset_ref_base" size="small"
        :disabled="step.config.offset_ref_tool" @change="onOffsetRefChange(step, 'base')">
        <span style="font-size: 11px">base_link</span>
      </el-checkbox>
      <el-checkbox v-model="step.config.offset_ref_tool" size="small"
        :disabled="step.config.offset_ref_base" @change="onOffsetRefChange(step, 'tool')">
        <span style="font-size: 11px">tool_link</span>
      </el-checkbox>
    </div>
    <el-row :gutter="6">
      <el-col :span="4" v-for="(f, fi) in poseFields" :key="'off_'+fi">
        <div style="font-size: 10px; color: #6b7b8d">d{{ f }}</div>
        <el-input v-model="step.config.offset[f]" :placeholder="'d'+f" size="small" />
      </el-col>
    </el-row>
  </template>

  <div style="font-size: 10px; color: #6b7b8d; margin-top: 4px">
    参考坐标系: {{ step.config.reference_frame || 'base_link' }}
  </div>
  <el-input v-model="step.config.reference_frame" placeholder="base_link" size="small" style="width: 200px; margin-top: 4px" />
</template>
```

- [ ] **Step 2: Update defaults in addStep()**

Update the upper_limb defaults:
```javascript
upper_limb: { mode: 'preset', arm: 'left', method: 'moveJ', preset_name: '', left_preset_name: '', right_preset_name: '', use_combined: true, use_composed_preset: false, reference_frame: 'base_link', left_reference_frame: 'base_link', right_reference_frame: 'base_link', position: {}, vision_source: '', left_vision_source: '', right_vision_source: '', pose_mode: 'manual', vision_step_label: '', enable_offset: false, offset_ref_base: true, offset_ref_tool: false, offset: {} },
```

- [ ] **Step 3: Update initialization in selectWorkflow()**

Add after the existing upper_limb init lines:
```javascript
if (s.type === 'upper_limb' && !s.config.pose_mode) s.config.pose_mode = 'manual'
if (s.type === 'upper_limb' && s.config.enable_offset == null) s.config.enable_offset = false
if (s.type === 'upper_limb' && s.config.offset_ref_base == null) s.config.offset_ref_base = true
if (s.type === 'upper_limb' && s.config.offset_ref_tool == null) s.config.offset_ref_tool = false
if (s.type === 'upper_limb' && !s.config.offset) s.config.offset = {}
```

- [ ] **Step 4: Add helper functions**

Add after `getPrecedingVisionSteps()`:

```javascript
// Vision step labels (for the dropdown in pose mode)
function getPrecedingVisionLabels(currentIdx) {
  if (!currentWorkflow.value?.steps) return []
  return currentWorkflow.value.steps
    .filter((s, i) => s.type === 'vision' && i < currentIdx)
}

function onPoseModeChange(step, mode) {
  if (mode !== 'vision') step.config.vision_step_label = ''
  if (mode === 'manual') {
    step.config.position = {}
  } else if (mode === 'current_ee') {
    step.config.position = {}
  }
}

function onVisionStepLabelChange(step, label) {
  // The step label is used at execution time to reference the vision output
  step.config.vision_step_label = label
  step.config.position = {}
}

function onOffsetToggle(step) {
  if (!step.config.enable_offset) {
    step.config.offset = {}
  }
}

function onOffsetRefChange(step, ref) {
  if (ref === 'base') {
    step.config.offset_ref_tool = false
  } else {
    step.config.offset_ref_base = false
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add robot_control/frontend/src/views/WorkflowEditor.vue
git commit -m "feat: add coordinate offset mode to upper limb workflow step"
```

---

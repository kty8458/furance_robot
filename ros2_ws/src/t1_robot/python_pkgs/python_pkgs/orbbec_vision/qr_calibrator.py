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
import cv2

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
                  stream_type: str = "color",
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

        frame = color_frame if stream_type == "color" else ir_frame
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
        # Convert translation from mm to meters: if abs(value) > 10, divide by 1000
        trans_m = np.array(trans, dtype=np.float64)
        for i in range(3):
            if abs(trans_m[i]) > 10:
                trans_m[i] /= 1000.0
        T_camera_ee = _make_transform(R_cam_ee, trans_m)
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
            stream_type=stream_type,
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
            "T_qr_workspace": T_qr_workspace.tolist()
        }

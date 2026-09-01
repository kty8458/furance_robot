"""现场标定模块 — 多 QR 支持，存储每个 QR 各自的 T_qr_ee。

流程:
  1. QRDetector 检测所有 QR (允许列表过滤)
  2. 获取 T_camera_ee: 调用方传入 TF 合成的当前值 (跨相机场景),
     或从 config 读取 eye-in-hand 常量
  3. 对每个检测到的 QR 多帧平均 → T_camera_qr_i
  4. T_qr_i_ee = inv(T_camera_qr_i) * T_camera_ee
  5. 存储 {qr_ids, T_qr_ee_per_id: {qr_id: T_qr_ee}}
  6. (可选, 提供 T_base_ee 时) 计算并存储场景级 T_base_qr_per_id,
     供二次标定使用: T_base_qr = T_base_ee @ inv(T_camera_ee) @ T_camera_qr

二次标定 (calibrate_secondary): 在相机看不到二维码的位置,
用已存储的场景级 T_base_qr 和当前 TF 的 T_base_ee 计算
  T_qr_ee_new = inv(T_base_qr) @ T_base_ee_now
使末端在任意位置获得与二维码的标定关系。

识别时每个 QR 独立算目标，再加权融合 + MAD 离群剔除。
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


def _pose_to_matrix(t: list[float], quat_xyzw: list[float]) -> np.ndarray:
    """translation [x,y,z] + quaternion [x,y,z,w] -> 4x4 齐次变换矩阵。"""
    qx, qy, qz, qw = quat_xyzw
    R = np.array([
        [1-2*qy*qy-2*qz*qz, 2*qx*qy-2*qz*qw, 2*qx*qz+2*qy*qw],
        [2*qx*qy+2*qz*qw, 1-2*qx*qx-2*qz*qz, 2*qy*qz-2*qx*qw],
        [2*qx*qz-2*qy*qw, 2*qy*qz+2*qx*qw, 1-2*qx*qx-2*qy*qy],
    ], dtype=np.float64)
    return _make_transform(R, np.array(t, dtype=np.float64))


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

    def calibrate(self, camera_id: str, arm: str,
                  qr_ids: list[int],
                  marker_size: float, point_name: str, scene_id: str,
                  stream_type: str = "color",
                  frames: Optional[list[np.ndarray]] = None,
                  T_base_ee: Optional[np.ndarray] = None,
                  T_camera_ee: Optional[np.ndarray] = None) -> dict:
        """
        多 QR 标定：为每个允许的 QR 独立计算 T_qr_ee 并存入字典。

        Args:
            camera_id: 相机 ID
            arm: "left" / "right"
            qr_ids: 允许参与的 QR ID 列表 (空表示通配, 接受所有检测到的)
            marker_size: QR 物理边长 (米)
            point_name: 标定点名称
            scene_id: 场景 ID
            stream_type: "color" / "ir"
            frames: 帧列表 (BGR 或灰度)
            T_base_ee: 采集时刻的 base->ee (由调用方从 TF 获取)
            T_camera_ee: 采集时刻的 camera->ee 4x4 变换。跨相机标定
                (相机不在被标定臂上) 时由调用方用 TF 链合成传入;
                None 时退回从 config 读取常量 (仅适用于相机装在
                被标定臂上的 eye-in-hand 场景)。

        Returns:
            {success, message, T_qr_ee_per_id, qr_ids_calibrated}
        """
        t0 = time.time()
        logger.info("calibrate: camera=%s arm=%s qr_ids=%s marker_size=%.4f point=%s scene=%s frames=%d",
                    camera_id, arm, qr_ids, marker_size, point_name, scene_id,
                    len(frames) if frames else 0)

        detector = self._detectors.get(camera_id)
        if detector is None:
            return {"success": False, "message": f"No intrinsics for camera: {camera_id}"}
        if not frames:
            return {"success": False, "message": "No frames available"}

        # 1. 对每个 QR id 收集多帧 tvec/rvec
        per_id_tvecs: dict[int, list[np.ndarray]] = {}
        per_id_rvecs: dict[int, list[np.ndarray]] = {}
        all_detected_ids: set[int] = set()  # 跟踪所有检测到的 ID, 用于错误提示
        for frame in frames:
            results = detector.detect(frame, marker_size)
            for r in results:
                all_detected_ids.add(r.qr_id)
                if qr_ids and r.qr_id not in qr_ids:
                    continue
                per_id_tvecs.setdefault(r.qr_id, []).append(np.asarray(r.tvec).ravel())
                per_id_rvecs.setdefault(r.qr_id, []).append(np.asarray(r.rvec).ravel())

        if not per_id_tvecs:
            detected_str = sorted(all_detected_ids) if all_detected_ids else "none"
            return {"success": False,
                    "message": f"No allowed QR detected. allowed={qr_ids or 'any'} actually_detected={detected_str}"}

        # 2. 获取 T_camera_ee: 优先用调用方 TF 合成的当前值 (跨相机场景),
        #    否则从 config 读取 eye-in-hand 常量
        if T_camera_ee is not None:
            T_camera_ee_mat = T_camera_ee
            logger.info("calibrate: T_camera_ee (caller-provided, cross-camera)=\n%s", T_camera_ee_mat)
        else:
            cfg = self._camera_configs.get(camera_id, {})
            calib = cfg.get("calibration", {})
            arm_letter = arm[0].upper() if arm else "R"
            ee_link = f"ARM-{arm_letter}-J7_Link"
            cam_to_ee = calib.get(f"camera_to_{ee_link}", {})
            if not cam_to_ee.get("translation"):
                return {"success": False, "message": f"No camera_to_ee calibration for {camera_id} → {ee_link}"}
            R_cam_ee, _ = cv2.Rodrigues(np.array(cam_to_ee["rotation"], dtype=np.float64))
            trans_m = np.array(cam_to_ee["translation"], dtype=np.float64)
            for i in range(3):
                if abs(trans_m[i]) > 10:
                    trans_m[i] /= 1000.0
            T_camera_ee_mat = _make_transform(R_cam_ee, trans_m)
            logger.info("calibrate: T_camera_ee (from config)=\n%s", T_camera_ee_mat)

        # 3. 每个 QR 独立平均 → T_qr_ee_i
        # OpenCV 光学系(X右/Y下/Z前) → ROS link 约定(X前/Y左/Z上)
        R_link_optical = np.array([
            [ 0,  0,  1],
            [-1,  0,  0],
            [ 0, -1,  0],
        ], dtype=np.float64)
        T_link_optical = np.eye(4); T_link_optical[:3, :3] = R_link_optical

        T_qr_ee_per_id: dict[str, dict] = {}
        T_base_qr_per_id: dict[str, dict] = {}
        for qid, tvecs in per_id_tvecs.items():
            if len(tvecs) < 3:
                logger.warning("calibrate: skip QR id=%d (only %d frames)", qid, len(tvecs))
                continue
            avg_tvec = np.mean(tvecs, axis=0)
            avg_rvec = np.mean(per_id_rvecs[qid], axis=0)
            R_cam_qr = _rodrigues_to_matrix(avg_rvec)
            T_camera_qr_optical = _make_transform(R_cam_qr, avg_tvec)
            # 光学系 → link 约定
            T_camera_qr = T_link_optical @ T_camera_qr_optical
            T_qr_ee = np.linalg.inv(T_camera_qr) @ T_camera_ee_mat
            t, r = _matrix_to_pose(T_qr_ee)
            T_qr_ee_per_id[str(qid)] = {"translation": t, "rotation": r}
            # 场景级 baselink->QR 变换 (供二次标定): T_base_qr = T_base_ee @ inv(T_camera_ee) @ T_camera_qr
            if T_base_ee is not None:
                T_base_qr = T_base_ee @ np.linalg.inv(T_camera_ee_mat) @ T_camera_qr
                tb, rb = _matrix_to_pose(T_base_qr)
                T_base_qr_per_id[str(qid)] = {"translation": tb, "rotation": rb}
            logger.info("calibrate: QR id=%d (%d frames) → T_qr_ee t=%s r=%s",
                        qid, len(tvecs), t, r)

        if not T_qr_ee_per_id:
            return {"success": False, "message": "No QR had enough frames for calibration"}

        # 4. 存储
        calibrated_ids = [int(k) for k in T_qr_ee_per_id.keys()]
        ok = self._scene.add_point(
            scene_id=scene_id,
            name=point_name,
            arm=arm,
            marker_size=marker_size,
            stream_type=stream_type,
            qr_ids=calibrated_ids,
            T_qr_ee_per_id=T_qr_ee_per_id,
            calib_type="primary",
        )
        if not ok:
            return {"success": False, "message": f"Failed to save point to scene {scene_id}"}
        # 场景级 T_base_qr (供二次标定), 每次正常标定刷新覆盖
        if T_base_qr_per_id:
            self._scene.set_base_qr_transforms(scene_id, T_base_qr_per_id)
            logger.info("calibrate: stored scene-level T_base_qr_per_id, ids=%s",
                        list(T_base_qr_per_id.keys()))
        else:
            logger.warning("calibrate: T_base_ee not available, T_base_qr_per_id not stored")

        elapsed = (time.time() - t0) * 1000
        logger.info("calibrate: done (%.1fms) calibrated %d QRs: %s",
                    elapsed, len(calibrated_ids), calibrated_ids)
        # 返回首个 QR 的结果用于前端预览
        first_qid = str(calibrated_ids[0])
        first = T_qr_ee_per_id[first_qid]
        return {
            "success": True,
            "message": f"Calibration complete ({len(calibrated_ids)} QRs)",
            "translation": first["translation"],
            "rotation": first["rotation"],
            "qr_ids_calibrated": calibrated_ids,
            "T_qr_ee_per_id": T_qr_ee_per_id,
            "T_base_qr_per_id": T_base_qr_per_id,
        }

    def calibrate_secondary(self, scene_id: str, source_point: str, point_name: str,
                            T_base_ee_now: np.ndarray,
                            arm: Optional[str] = None) -> dict:
        """二次标定: 在相机看不到二维码的位置, 用已存储的 T_base_qr 计算新点位。

        前提: 该场景已完成一次正常标定 (存储了场景级 T_base_qr_per_id),
        且主标定后底盘未移动 (T_base_qr 依赖底盘位置)。

        数学: T_qr_ee_new = inv(T_base_qr_stored) @ T_base_ee_now
        marker_size/stream_type/qr_ids 继承自 source_point;
        arm 默认继承 source_point, 传入 "left"/"right" 时覆盖 —
        用于头部/对侧相机观察二维码时为另一只臂生成新点位。

        Returns:
            {success, message, translation, rotation, qr_ids_calibrated, T_qr_ee_per_id}
        """
        t0 = time.time()
        logger.info("calibrate_secondary: scene=%s source=%s point=%s arm_override=%s",
                    scene_id, source_point, point_name, arm)

        if T_base_ee_now is None:
            return {"success": False, "message": "TF lookup failed: base_link to ee_link"}

        # 1. 场景级 T_base_qr (须先完成正常标定)
        T_base_qr_per_id = self._scene.get_base_qr_transforms(scene_id)
        if not T_base_qr_per_id:
            return {"success": False,
                    "message": f"Scene '{scene_id}' has no stored T_base_qr. "
                               "Run a normal calibration at an observation pose first."}

        # 2. 源点位 (继承参数)
        src_point = self._scene.find_point(scene_id, source_point)
        if src_point is None:
            return {"success": False,
                    "message": f"Source point '{source_point}' not found in scene '{scene_id}'"}

        # 3. 逐 QR 计算 T_qr_ee_new = inv(T_base_qr) @ T_base_ee_now
        T_qr_ee_per_id: dict[str, dict] = {}
        for qid, pose in T_base_qr_per_id.items():
            try:
                T_base_qr = _pose_to_matrix(pose["translation"], pose["rotation"])
            except Exception:
                logger.warning("calibrate_secondary: skip QR id=%s (bad stored pose)", qid)
                continue
            T_qr_ee_new = np.linalg.inv(T_base_qr) @ T_base_ee_now
            t, r = _matrix_to_pose(T_qr_ee_new)
            T_qr_ee_per_id[str(qid)] = {"translation": t, "rotation": r}
            logger.info("calibrate_secondary: QR id=%s -> T_qr_ee t=%s r=%s", qid, t, r)

        if not T_qr_ee_per_id:
            return {"success": False, "message": "No valid stored T_base_qr to compute from"}

        # 4. 存储 (calib_type=secondary, 继承源点位参数; arm 可被调用方覆盖)
        stored_arm = src_point.get("arm", "right")
        if arm in ("left", "right"):
            if arm != stored_arm:
                logger.info("calibrate_secondary: arm override %s -> %s", stored_arm, arm)
            stored_arm = arm
        calibrated_ids = [int(k) for k in T_qr_ee_per_id.keys()]
        ok = self._scene.add_point(
            scene_id=scene_id,
            name=point_name,
            arm=stored_arm,
            marker_size=src_point.get("marker_size", 0.058),
            stream_type=src_point.get("stream_type", "color"),
            qr_ids=src_point.get("qr_ids", calibrated_ids),
            T_qr_ee_per_id=T_qr_ee_per_id,
            calib_type="secondary",
            source_point=source_point,
        )
        if not ok:
            return {"success": False, "message": f"Failed to save point to scene {scene_id}"}

        elapsed = (time.time() - t0) * 1000
        logger.info("calibrate_secondary: done (%.1fms) calibrated %d QRs: %s",
                    elapsed, len(calibrated_ids), calibrated_ids)
        first_qid = str(calibrated_ids[0])
        first = T_qr_ee_per_id[first_qid]
        return {
            "success": True,
            "message": f"Secondary calibration complete ({len(calibrated_ids)} QRs)",
            "translation": first["translation"],
            "rotation": first["rotation"],
            "qr_ids_calibrated": calibrated_ids,
            "T_qr_ee_per_id": T_qr_ee_per_id,
        }

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
    """ArUco 二维码检测器 — AprilTag tag36h11。

    使用 cv2.aruco.ArucoDetector 检测，
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
        self.aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_APRILTAG_36H11)
        self.detector = aruco.ArucoDetector(self.aruco_dict)
        logger.info("QRDetector initialized: fx=%.2f fy=%.2f cx=%.2f cy=%.2f dict=APRILTAG_36H11",
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

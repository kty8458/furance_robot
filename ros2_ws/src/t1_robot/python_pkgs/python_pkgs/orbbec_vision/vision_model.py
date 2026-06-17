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

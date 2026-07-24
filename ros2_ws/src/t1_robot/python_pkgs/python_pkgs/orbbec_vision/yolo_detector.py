"""YOLO 分割检测模块 - ultralytics 后端, 供点云模块与标注流使用。

参考 qr_detector.py 的模块风格:
  - detect(image) -> list[YOLOResult]
  - draw_results(image, results) -> 标注图 (掩码叠加 + 框 + 类名)

推理用 ultralytics.YOLO(.onnx): 官方后处理(NMS/掩码解码)100%正确, 无需手写。
ultralytics 加载 .onnx 时用 onnxruntime, 不依赖 torch (仅 .pt 才需 torch)。
"""

import logging
import time
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger("orbbec_vision.yolo_detector")


@dataclass
class YOLOResult:
    """单个检测目标 (分割)。"""
    class_id: int
    class_name: str
    conf: float
    bbox: list  # [x1, y1, x2, y2] 原图像素坐标
    mask: np.ndarray  # (H, W) bool, 原图尺寸, 已 crop 到 bbox
    mask_area_px: int = 0  # 掩码像素数 (点云模块可据此判断可见面积)


# 按类别上色 (BGR), 超出类别数则循环取色
_DEFAULT_COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 255),
    (255, 0, 255), (255, 255, 0), (0, 165, 255), (255, 165, 0),
]


def _color(cls: int) -> tuple:
    return _DEFAULT_COLORS[cls % len(_DEFAULT_COLORS)]


class YOLODetector:
    """YOLOv8-seg 分割检测器 (ultralytics 后端)。

    Args:
        model_path: best.onnx (或 .pt) 路径
        names: 类别名 (列表或字典), 用于覆盖/显示; 不传则用模型自带 names
        conf: 置信度阈值
        iou: NMS IoU 阈值
        imgsz: 推理尺寸 (32 倍数, 与导出一致)
        device: 'cpu' / 'cuda' / '0' 等 (ultralytics device 参数)
    """

    def __init__(self, model_path: str, names=None, conf: float = 0.5,
                 iou: float = 0.45, imgsz: int = 640, device: str = "cpu"):
        from ultralytics import YOLO

        self.model_path = str(model_path)
        self.conf = conf
        self.iou = iou
        self.imgsz = int(imgsz)
        self.device = device
        self._custom_names = self._resolve_names(names)

        try:
            # onnx 丢失 task 元数据, 需显式指定; .pt 自动识别
            self._model = YOLO(self.model_path, task="segment")
        except Exception as e:
            logger.exception("Failed to load model: %s", self.model_path)
            raise RuntimeError(f"YOLO load failed: {e}") from e

        # 任务类型: detect / segment
        self._task = getattr(self._model, "task", "segment")
        # names: 优先自定义, 否则用模型自带 (onnx 可能丢失, 用自定义补)
        self._names = self._custom_names or {
            int(k): str(v) for k, v in (self._model.names or {}).items()
        } or {0: "object"}
        logger.info("YOLODetector ready: model=%s task=%s names=%s conf=%.2f iou=%.2f imgsz=%d device=%s",
                    self.model_path, self._task, self._names, self.conf, self.iou, self.imgsz, self.device)

    @staticmethod
    def _resolve_names(names) -> dict:
        if not names:
            return {}
        if isinstance(names, dict):
            return {int(k): str(v) for k, v in names.items()}
        if isinstance(names, (list, tuple)):
            return {i: str(n) for i, n in enumerate(names)}
        return {0: str(names)}

    def name(self, class_id: int) -> str:
        return self._names.get(class_id, f"class_{class_id}")

    # ---- 公共 API ----

    def detect(self, image: np.ndarray) -> list:
        """检测分割目标。

        Args:
            image: BGR 彩色图 (H,W,3) 或灰度 (H,W) (灰度转 BGR)
        Returns:
            list[YOLOResult], 按 conf 降序
        """
        if image is None or image.size == 0:
            return []
        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        elif image.shape[2] == 4:
            image = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

        t0 = time.time()
        results = self._model.predict(
            image, conf=self.conf, iou=self.iou, imgsz=self.imgsz,
            device=self.device, verbose=False, retina_masks=True,
        )
        elapsed = (time.time() - t0) * 1000
        out = self._parse(results[0], image.shape[:2])
        out.sort(key=lambda r: r.conf, reverse=True)
        logger.info("detect: %d targets (%.1fms)", len(out), elapsed)
        return out

    def _parse(self, result, orig_shape) -> list:
        """解析 ultralytics Result -> list[YOLOResult]。"""
        h, w = orig_shape
        out: list[YOLOResult] = []
        if result.boxes is None or len(result.boxes) == 0:
            return out
        boxes_xyxy = result.boxes.xyxy.cpu().numpy()  # [N,4]
        confs = result.boxes.conf.cpu().numpy()       # [N]
        cls_ids = result.boxes.cls.cpu().numpy().astype(int)  # [N]

        masks = None
        if self._task == "segment" and result.masks is not None and len(result.masks) > 0:
            # masks.data: [N, H, W] (原图尺寸, retina_masks=True 时)
            masks = result.masks.data.cpu().numpy().astype(bool)

        for i in range(len(boxes_xyxy)):
            mask = masks[i] if (masks is not None and i < len(masks)) else np.zeros((h, w), dtype=bool)
            cid = int(cls_ids[i])
            out.append(YOLOResult(
                class_id=cid,
                class_name=self.name(cid),
                conf=float(confs[i]),
                bbox=[float(v) for v in boxes_xyxy[i]],
                mask=mask,
                mask_area_px=int(mask.sum()),
            ))
        return out

    def draw_results(self, image: np.ndarray, results: list,
                     alpha: float = 0.5) -> np.ndarray:
        """掩码半透明叠加 + 框 + 类名置信度。

        Args:
            image: BGR 彩色图 (H,W,3) 或灰度 (H,W)
            results: detect() 返回值
            alpha: 掩码叠加透明度
        Returns:
            BGR 标注图
        """
        if image.ndim == 2:
            out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            out = image.copy()
        overlay = out.copy()
        for r in results:
            c = _color(r.class_id)
            if r.mask.any():
                overlay[r.mask] = c
            x1, y1, x2, y2 = [int(v) for v in r.bbox]
            cv2.rectangle(out, (x1, y1), (x2, y2), c, 2)
            label = f"{r.class_name} {r.conf:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(out, (x1, max(0, y1 - th - 6)), (x1 + tw + 4, y1), c, -1)
            cv2.putText(out, label, (x1 + 2, y1 - 4 if y1 - 4 > th else y1 + th),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        mask_any = np.zeros(out.shape[:2], dtype=bool)
        for r in results:
            mask_any |= r.mask
        if mask_any.any():
            cv2.addWeighted(overlay, alpha, out, 1 - alpha, 0, dst=out)
        return out


__all__ = ["YOLODetector", "YOLOResult"]

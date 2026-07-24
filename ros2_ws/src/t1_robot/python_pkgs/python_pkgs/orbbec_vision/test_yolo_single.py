#!/usr/bin/env python3
"""
YOLO 分割单帧测试 - 连相机取一帧彩色图, 跑分割检测, 输出标注图用于查看效果。

调用本模块 yolo_detector.YOLODetector (与 camera_manager_node 实际使用的同一模块,
修改直接同步)。

用法:
  # 默认: head 相机, 模型 models/train/weights/best.onnx, 输出 yolo_test_out.jpg
  python3 test_yolo_single.py

  # 指定相机 / 模型 / 输出
  python3 test_yolo_single.py --camera right_arm --model /abs/path/best.onnx --out result.jpg

  # 不连相机, 直接对已有图片跑检测
  python3 test_yolo_single.py --image /path/to/img.jpg --model best.onnx --out result.jpg

依赖: pyorbbecsdk (取相机帧时), onnxruntime (推理)。
模型未训练/缺失时: 仅 --image 模式可用空模型测试会报错; 相机模式会先校验模型存在。
"""

import argparse
import os
import sys

# ---- pyorbbecsdk 原生库路径修复 (须在 import pyorbbecsdk 前) ----
_SDK_LIB_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "lib", "python3.10",
    "site-packages", "pyorbbecsdk",
)
if os.path.isdir(_SDK_LIB_DIR):
    _ld = os.environ.get("LD_LIBRARY_PATH", "")
    if _SDK_LIB_DIR not in _ld.split(":"):
        os.environ["LD_LIBRARY_PATH"] = f"{_SDK_LIB_DIR}:{_ld}" if _ld else _SDK_LIB_DIR
        os.execve(sys.executable, [sys.executable] + sys.argv, os.environ)

import cv2
import numpy as np

# ---- 导入 YOLO 检测模块 (与 camera_manager_node 同源) ----
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
from yolo_detector import YOLODetector

# ---- 默认配置 (与 yolo_config.yaml 一致) ----
DEFAULT_MODEL = os.path.join(_here, "models", "train", "weights", "best.onnx")
DEFAULT_NAMES = ["pole"]
DEFAULT_CONF = 0.5
DEFAULT_IOU = 0.45
DEFAULT_IMGSZ = 640
DEFAULT_OUT = os.path.join(_here, "yolo_test_out.jpg")


def parse_args():
    p = argparse.ArgumentParser(description="YOLO 分割单帧测试: 取一帧 -> 分割 -> 输出标注图")
    p.add_argument("--camera", default="head", help="相机 id (head/left_arm/right_arm), 仅相机模式")
    p.add_argument("--model", default=DEFAULT_MODEL, help="best.onnx 路径")
    p.add_argument("--names", default=",".join(DEFAULT_NAMES), help="类别名, 逗号分隔")
    p.add_argument("--conf", type=float, default=DEFAULT_CONF)
    p.add_argument("--iou", type=float, default=DEFAULT_IOU)
    p.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    p.add_argument("--image", default=None, help="直接用本地图片 (跳过相机采集)")
    p.add_argument("--out", default=DEFAULT_OUT, help="输出标注图路径")
    p.add_argument("--show", action="store_true", help="弹窗显示 (无头环境慎用)")
    return p.parse_args()


def detect_on_image(detector: YOLODetector, img: np.ndarray, out_path: str, show: bool):
    """对单张图跑检测并保存标注图。"""
    print(f"[输入] 图像尺寸: {img.shape[1]}x{img.shape[0]}")
    results = detector.detect(img)
    print(f"[检测] 共 {len(results)} 个目标:")
    for i, r in enumerate(results):
        x1, y1, x2, y2 = [int(v) for v in r.bbox]
        print(f"  [{i}] {r.class_name} conf={r.conf:.3f} "
              f"box=({x1},{y1})-({x2},{y2}) mask_area={r.mask_area_px}px")

    annotated = detector.draw_results(img, results)
    cv2.imwrite(out_path, annotated)
    print(f"[输出] 标注图已保存: {out_path}")
    if show:
        cv2.imshow("YOLO seg", annotated)
        print("[显示] 按任意键关闭窗口")
        cv2.waitKey(0)
        cv2.destroyAllWindows()


def grab_one_frame_from_camera(camera_id: str) -> np.ndarray:
    """复用 CameraManager 启动彩色流, 等一帧新数据后返回 BGR 图。"""
    import time
    # 复用 camera_manager_node 的 CameraManager (它内部用 python_pkgs.orbbec_vision.* 路径导入,
    # 需把 python_pkgs 包根加进 sys.path)
    _pkgs_root = os.path.normpath(os.path.join(_here, ".."))
    if _pkgs_root not in sys.path:
        sys.path.insert(0, _pkgs_root)
    from python_pkgs.orbbec_vision.camera_manager_node import CameraManager

    config_path = os.environ.get("CAMERA_CONFIG_PATH", "")
    if not config_path:
        config_path = os.path.join(_here, "camera_config.yaml")
    print(f"[相机] 初始化 CameraManager (config={config_path}) ...")
    manager = CameraManager(config_path)

    cam_ids = [c["id"] for c in manager.get_camera_list()]
    print(f"[相机] 已连接: {cam_ids}")
    if camera_id not in cam_ids:
        raise RuntimeError(f"相机 '{camera_id}' 未连接或不存在, 可用: {cam_ids}")

    print(f"[相机] 启动 {camera_id} 彩色流 ...")
    r = manager.start_stream(camera_id, "raw")
    if not r["success"]:
        raise RuntimeError(f"启动流失败: {r['message']}")

    # 等第一帧新数据 (最多 ~3s)
    print("[相机] 等待首帧 ...")
    frame = None
    for _ in range(60):
        frame = manager.get_latest_color(camera_id)
        if frame is not None:
            break
        time.sleep(0.05)
    if frame is None:
        manager.stop_stream(camera_id)
        raise RuntimeError("取帧超时, 未拿到彩色帧")

    # 再等一帧确保不是启动残留
    last_ts = manager.get_frame_timestamp(camera_id)
    t0 = time.time()
    while manager.get_frame_timestamp(camera_id) == last_ts:
        if time.time() - t0 > 2.0:
            break
        time.sleep(0.02)
    frame = manager.get_latest_color(camera_id)
    manager.stop_stream(camera_id)
    print(f"[相机] 取帧成功: {frame.shape[1]}x{frame.shape[0]}")
    return frame


def main():
    args = parse_args()

    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if not os.path.isfile(args.model):
        print(f"[错误] 模型不存在: {args.model}")
        print("       训练完成后产物在 models/train/weights/best.onnx,")
        print("       或用 --model 指定路径 / --image 用本地图片测试。")
        sys.exit(1)

    print(f"[模型] {args.model}")
    print(f"[参数] names={names} conf={args.conf} iou={args.iou} imgsz={args.imgsz}")
    detector = YOLODetector(
        model_path=args.model, names=names,
        conf=args.conf, iou=args.iou, imgsz=args.imgsz, device="cpu",
    )

    if args.image:
        img = cv2.imread(args.image)
        if img is None:
            print(f"[错误] 读图失败: {args.image}")
            sys.exit(1)
    else:
        img = grab_one_frame_from_camera(args.camera)

    detect_on_image(detector, img, args.out, args.show)
    print("[完成]")


if __name__ == "__main__":
    main()

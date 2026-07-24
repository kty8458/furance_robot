#!/usr/bin/env python3
"""
YOLO 训练脚本 (单次使用, 不集成进系统)。

用途: 为「长杆物件抓取」采集的彩色帧训练 YOLO 分割模型, 训练产物供
后续 yolo 分割 + 点云匹配方案使用。

== 目录约定 (均相对于本脚本所在目录) ==
  data/yolo/      标注好的数据集 (YOLO 格式), 不存在时自动创建
  models/         训练产物 (best.pt / last.pt / best.onnx), 不存在时自动创建

== 数据集格式 ==
推荐: 直接放一个 data.yaml 进 data/yolo/ (Roboflow/LabelImg 导出即自带),
      脚本直接使用。若无 data.yaml, 脚本会按以下标准布局自动生成:
      data/yolo/
        images/train/  images/val/   (彩色图 *.jpg)
        labels/train/  labels/val/   (标注 *.txt, 每行: cls x y w h 或分割点)
      只有 images/ + labels/ 扁平结构时, 加 --val-split 0.2 可自动 8:2 拆分。

== 典型用法 ==
  # 分割 (默认), nano 权重, 100 轮, 类别名 pole
  python3 train_yolo.py --names pole

  # 指定已有 data.yaml + 更大模型 + 更多轮次
  python3 train_yolo.py --data data/yolo/my.yaml --model yolov8s-seg --epochs 200

  # 检测任务 (而非分割)
  python3 train_yolo.py --task detect --names pole,bracket

  # 扁平数据集自动拆分验证集
  python3 train_yolo.py --val-split 0.2 --names pole

依赖: pip install ultralytics (会自动装 torch; 想用 GPU 装对应 CUDA 版 torch)
"""

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data" / "yolo"
MODELS_DIR = SCRIPT_DIR / "models"
IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".webp")


def ensure_dirs():
    """确保 data/yolo 与 models 目录存在。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[目录] 数据集: {DATA_DIR}")
    print(f"[目录] 模型输出: {MODELS_DIR}")


def _glob_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    out = []
    for ext in IMG_EXTS:
        out.extend(folder.glob(f"*{ext}"))
        out.extend(folder.glob(f"*{ext.upper()}"))
    return sorted(set(out))


def _collect_classes(label_dirs: list[Path]) -> list[int]:
    """扫描标签文件, 收集所有出现过的类别 id (升序)。"""
    ids = set()
    for d in label_dirs:
        if not d.is_dir():
            continue
        for txt in d.glob("*.txt"):
            try:
                for line in txt.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line:
                        ids.add(int(line.split()[0]))
            except (ValueError, OSError):
                continue
    return sorted(ids)


def _write_data_yaml(path: Path, train_rel: str, val_rel: str, names: dict[int, str]):
    """写出 ultralytics data.yaml (纯文本, 无需 pyyaml)。"""
    lines = [
        "# 自动生成于 train_yolo.py, 可按需修改",
        f"path: {DATA_DIR.as_posix()}",
        f"train: {train_rel}",
        f"val: {val_rel}",
        "names:",
    ]
    for cid, name in sorted(names.items()):
        lines.append(f"  {cid}: {name}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[data.yaml] 已生成: {path}")
    for ln in lines:
        print(f"    {ln}")


def resolve_dataset(args) -> Path:
    """返回 data.yaml 路径: 优先用 --data 或现有 data.yaml, 否则自动生成。"""
    # 1) 显式指定或已存在的 data.yaml
    yaml_candidate = Path(args.data) if args.data else (DATA_DIR / "data.yaml")
    if yaml_candidate.exists():
        print(f"[数据集] 使用现有 data.yaml: {yaml_candidate}")
        return yaml_candidate
    if args.data:
        sys.exit(f"[错误] 指定的 data.yaml 不存在: {args.data}")

    # 2) 自动生成: 标准布局 images/{train,val} + labels/{train,val}
    images_dir = DATA_DIR / "images"
    labels_dir = DATA_DIR / "labels"
    if not images_dir.is_dir():
        sys.exit(
            f"[错误] 未找到数据集。请把 YOLO 格式数据放入:\n"
            f"  {DATA_DIR}\n"
            f"  期望: data.yaml 或 images/train(,images/val) + labels/train(,labels/val)\n"
            f"  或用 --data 指定已有 data.yaml。"
        )

    train_img_dir = images_dir / "train"
    val_img_dir = images_dir / "val"

    # 2a) 扁平布局 -> 自动拆分验证集
    flat_imgs = _glob_images(images_dir)
    if not train_img_dir.is_dir() and not val_img_dir.is_dir() and flat_imgs:
        if args.val_split and 0 < args.val_split < 1:
            _auto_split(flat_imgs, images_dir, labels_dir, args.val_split)
            train_img_dir = images_dir / "train"
            val_img_dir = images_dir / "val"
        else:
            sys.exit(
                "[错误] 扁平 images/ 布局需指定 --val-split (如 0.2) 才能自动拆分, "
                "或先按 images/train,images/val 组织数据。"
            )

    train_imgs = _glob_images(train_img_dir)
    val_imgs = _glob_images(val_img_dir)
    if not train_imgs:
        sys.exit(f"[错误] {train_img_dir} 下无图片。")
    if not val_imgs:
        print("[警告] 无验证集 (images/val 为空), 将用训练集作验证 (val=train)。")

    # 类别名: --names 优先, 否则扫描标签自动取名 class_<id>
    label_dirs = [labels_dir / "train", labels_dir / "val"]
    cls_ids = _collect_classes(label_dirs) or [0]
    if args.names:
        names_list = [n.strip() for n in args.names.split(",") if n.strip()]
        names = {cid: names_list[cid] if cid < len(names_list) else f"class_{cid}"
                 for cid in cls_ids}
    else:
        names = {cid: f"class_{cid}" for cid in cls_ids}

    val_rel = "images/val" if val_imgs else "images/train"
    out_yaml = DATA_DIR / "data.yaml"
    _write_data_yaml(out_yaml, "images/train", val_rel, names)
    return out_yaml


def _auto_split(imgs: list[Path], images_dir: Path, labels_dir: Path, val_split: float):
    """把扁平 images/+labels/ 按 val_split 拆成 train/val (用符号链接, 不复制原图)。"""
    import random
    n_val = max(1, int(len(imgs) * val_split))
    idx = list(range(len(imgs)))
    random.seed(42)
    random.shuffle(idx)
    val_idx = set(idx[:n_val])

    (images_dir / "train").mkdir(parents=True, exist_ok=True)
    (images_dir / "val").mkdir(parents=True, exist_ok=True)
    (labels_dir / "train").mkdir(parents=True, exist_ok=True)
    (labels_dir / "val").mkdir(parents=True, exist_ok=True)

    for i, img in enumerate(imgs):
        split = "val" if i in val_idx else "train"
        # 图片软链
        dst_img = images_dir / split / img.name
        if not dst_img.exists():
            dst_img.symlink_to(img.resolve())
        # 标签文件同名 .txt 软链
        lbl = labels_dir / (img.stem + ".txt")
        if lbl.exists():
            dst_lbl = labels_dir / split / lbl.name
            if not dst_lbl.exists():
                dst_lbl.symlink_to(lbl.resolve())
    print(f"[拆分] {len(imgs)} 张 -> train {len(imgs) - n_val} / val {n_val} (符号链接)")


def validate_dataset(yaml_path: Path):
    """简单核对: train 图片数, 抽查标签是否一一对应。

    数据根目录优先取 data.yaml 的 path 字段 (绝对路径), 否则用脚本默认 DATA_DIR。
    """
    data_root = DATA_DIR
    try:
        for line in yaml_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("path:"):
                p = line.split(":", 1)[1].strip()
                if p:
                    data_root = Path(p).expanduser()
                    if not data_root.is_absolute():
                        data_root = (yaml_path.parent / p).resolve()
                break
    except OSError:
        pass

    train_img_dir = data_root / "images" / "train"
    val_img_dir = data_root / "images" / "val"
    n_train = len(_glob_images(train_img_dir))
    n_val = len(_glob_images(val_img_dir)) if val_img_dir.is_dir() else 0
    print(f"[校验] data_root={data_root}")
    print(f"[校验] train 图片 {n_train} 张, val 图片 {n_val} 张")
    if n_train == 0:
        sys.exit("[错误] 训练集为空, 终止。")
    # 抽查标签存在性
    sample = _glob_images(train_img_dir)[:3]
    missing = 0
    for img in sample:
        lbl = data_root / "labels" / "train" / (img.stem + ".txt")
        if not lbl.exists():
            missing += 1
    if missing == len(sample) and sample:
        print("[警告] 抽查的训练图片均未找到对应 labels/train/<name>.txt, "
              "请确认标注文件已就位 (ultralytics 会因缺标签而警告)。")
    print(f"[校验] data.yaml: {yaml_path}")


def train(args, yaml_path: Path) -> Path:
    """执行训练, 返回 best.pt 路径。"""
    from ultralytics import YOLO

    print(f"\n[训练] task={args.task} model={args.model} epochs={args.epochs} "
          f"imgsz={args.imgsz} batch={args.batch} device={args.device or 'auto'}")
    # 预训练权重: ultralytics 会自动下载 (联网首次)
    model = YOLO(args.model)
    results = model.train(
        data=str(yaml_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device or None,
        project=str(MODELS_DIR),
        name="train",
        exist_ok=True,
        patience=args.patience,
        workers=args.workers,
    )
    # ultralytics 默认把产物写到 MODELS_DIR/train/weights/best.pt
    best = MODELS_DIR / "train" / "weights" / "best.pt"
    last = MODELS_DIR / "train" / "weights" / "last.pt"
    if not best.exists() and results is not None:
        # 某些版本 save 路径在 results.save_dir
        best = Path(getattr(results, "save_dir", MODELS_DIR)) / "weights" / "best.pt"
    if not best.exists():
        sys.exit(f"[错误] 训练结束但未找到 best.pt, 请检查 {MODELS_DIR}/train 下产物。")
    print(f"[训练] 完成, best.pt: {best}")
    if last.exists():
        print(f"[训练] last.pt: {last}")
    return best


def export_onnx(best_pt: Path, args):
    """导出 onnx (推理端 yolo_dete.py 用的就是 onnx)。"""
    from ultralytics import YOLO
    print(f"\n[导出] {best_pt} -> onnx (dynamic=True)")
    model = YOLO(str(best_pt))
    kwargs = {"format": "onnx", "dynamic": True}
    if args.simplify:
        kwargs["simplify"] = True
    if args.half:
        kwargs["half"] = True
    try:
        onnx_path = model.export(**kwargs)
        print(f"[导出] onnx: {onnx_path}")
    except Exception as e:
        print(f"[警告] onnx 导出失败 (可稍后用 vision/pt2onnx.py 手动导出): {e}")


def parse_args():
    p = argparse.ArgumentParser(
        description="YOLO 训练脚本 (单次使用)。数据在 data/yolo, 模型输出到 models。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--task", choices=["segment", "detect"], default="segment",
                   help="任务类型: 分割 (长杆抓取方案) 或 检测")
    p.add_argument("--model", default=None,
                   help="预训练权重名/路径; 不填则按 task 自动选 yolov8n-seg / yolov8n")
    p.add_argument("--data", default=None,
                   help="data.yaml 路径; 不填则用 data/yolo/data.yaml 或自动生成")
    p.add_argument("--names", default=None,
                   help="类别名, 逗号分隔, 如 'pole,bracket'; 不填则扫描标签取名 class_<id>")
    p.add_argument("--val-split", type=float, default=None,
                   help="扁平 images/+labels/ 时自动按比例拆验证集, 如 0.2")
    p.add_argument("--epochs", type=int, default=100, help="训练轮数")
    p.add_argument("--imgsz", type=int, default=640, help="训练图像尺寸")
    p.add_argument("--batch", type=int, default=16, help="batch (-1 自动)")
    p.add_argument("--device", default=None, help="设备, 如 0 / 0,1 / cpu; 空=自动")
    p.add_argument("--patience", type=int, default=30, help="早停耐心值 (0=关闭)")
    p.add_argument("--workers", type=int, default=8, help="dataloader 进程数")
    p.add_argument("--no-onnx", action="store_true", help="不导出 onnx (默认导出)")
    p.add_argument("--simplify", action="store_true", default=True, help="onnx 简化 (onnxsim)")
    p.add_argument("--half", action="store_true", help="onnx 导出 fp16 (需 GPU)")
    p.add_argument("--dry-run", action="store_true", help="只校验数据集与配置, 不训练")
    return p.parse_args()


def main():
    args = parse_args()
    ensure_dirs()

    # 默认权重按任务选
    if args.model is None:
        args.model = "yolov8n-seg" if args.task == "segment" else "yolov8n"
    # ultralytics 检测模型名带 -pt, 分割带 -seg; 做个温和提示
    if args.task == "segment" and "-seg" not in args.model and not Path(args.model).exists():
        print(f"[提示] task=segment 但 model={args.model} 非 -seg 权重, 确认是否正确。")

    yaml_path = resolve_dataset(args)
    validate_dataset(yaml_path)

    if args.dry_run:
        print("\n[dry-run] 配置就绪, 未训练。去掉 --dry-run 开始训练。")
        return

    best_pt = train(args, yaml_path)
    if not args.no_onnx:
        export_onnx(best_pt, args)

    print("\n[完成] 产物在 models/ 下。")
    print("  - best.pt: PyTorch 权重, 可继续微调或用 pt2onnx.py 转 onnx")
    print("  - best.onnx: 推理用 (yolo_dete.py 的 detect_model_path 指向它)")
    print(f"  - data.yaml: {yaml_path}")


if __name__ == "__main__":
    main()

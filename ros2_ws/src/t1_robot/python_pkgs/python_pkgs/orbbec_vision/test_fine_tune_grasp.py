#!/usr/bin/env python3
"""取样杆微调抓取 - 闭环二次对齐单帧测试。

前置条件: 臂已通过 QR 标定移动到预抓取位 (本脚本不做 QR 定位, 也不做伸进/闭爪)。

流程 (分阶段闭环, 每阶段最多 --max-iter 次):
  阶段1 roll 对齐: 取一帧, YOLO 分割 mask, mask 像素 PCA 求杆中轴线,
    杆轴与图像竖直方向 (对称轴 u=W/2) 的夹角 -> 绕 tool x 轴旋转, 位置不动只调姿态
  阶段2 y 对齐 (roll 转正后才测 y, 避免倾斜时中线处 dy 测量被杠杆臂污染):
    杆轴线在图像中线行的 u 偏差 x 深度/fx -> tool y 增量 (mm),
    扣除 --cam-y-offset (RGB 镜头相对夹爪中心的横向偏移)
  阶段3 深度进给: 沿杆轴采样深度取中位数,
    dz = (测量深度 - 参考深度) + --depth-offset (抓取点相对镜头的深度偏移),
    |dz| > --depth-tol 报错拒动, 否则沿深度轴进给
  所有增量经 T_target = T_base_ee @ T_offset (tool 系) 换算 base 系,
    通过 /move_pose 下发 (与工作流上肢 tool 偏移同一数学)

--dry-run: 只计算并打印增量 + 输出可视化图, 不动臂。
依赖: pyorbbecsdk, onnxruntime(经 yolo_detector), rclpy, control_interfaces, tf2_ros
"""

import argparse
import math
import os
import sys
import threading
import time

# ---- pyorbbecsdk 原生库路径修复 (须在 import 前) ----
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

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
from yolo_detector import YOLODetector
from test_grasp_single import (MIN_DEPTH_M, MAX_DEPTH_M, load_intrinsics)
from fine_tune_measure import (
    MAX_ROLL_ERR_DEG, mask_axis, measure, draw_viz, load_fine_tune_cfg,
)

DEFAULT_MODEL = os.path.join(_here, "models", "train", "weights", "best.onnx")
DEFAULT_NAMES = ["gan 1"]
DEFAULT_CFG = os.path.join(_here, "camera_config.yaml")


def new_out_prefix() -> str:
    """默认输出前缀: data/fine_tune/<时间戳>/fine_tune, 每次运行新目录不覆盖。"""
    out_dir = os.path.join(_here, "data", "fine_tune", time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    print(f"[输出] 本次可视化目录: {out_dir}")
    return os.path.join(out_dir, "fine_tune")

def parse_args():
    p = argparse.ArgumentParser(description="取样杆闭环微调抓取单帧测试 (仅微调段)")
    p.add_argument("--camera", default="right_arm")
    p.add_argument("--arm", default="right", choices=["left", "right"])
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--names", default=",".join(DEFAULT_NAMES))
    p.add_argument("--config", default=DEFAULT_CFG, help="camera_config.yaml 路径")
    p.add_argument("--conf", type=float, default=0.5)
    p.add_argument("--out", default=None,
                   help="可视化图输出路径前缀 (默认 data/fine_tune/<时间戳>/)")
    # ---- 微调参数 ----
    p.add_argument("--ref-depth", type=float, required=True,
                   help="手动标定的参考深度 (米), 与测量深度之差为深度增量")
    p.add_argument("--cam-y-offset", type=float, default=None,
                   help="RGB 镜头相对夹爪中心的横向偏移 (mm), "
                        "dy 有效值 = 测量 dy - 此值 (默认读 camera_config.yaml "
                        "对应相机 fine_tune.cam_y_offset_mm)")
    p.add_argument("--depth-offset", type=float, default=None,
                   help="抓取点相对镜头光心的深度偏移 (mm), 正值=抓取点比镜头更远"
                        "(需多进给), dz = (测量-参考)x1000 + 此值 "
                        "(默认读 camera_config.yaml fine_tune.depth_offset_mm)")
    p.add_argument("--depth-tol", type=float, default=0.030,
                   help="深度增量容差 (米), 超出报错拒动 (默认 0.030)")
    p.add_argument("--roll-tol", type=float, default=1.0, help="roll 收敛阈值 (度)")
    p.add_argument("--y-tol", type=float, default=2.0, help="y 收敛阈值 (mm)")
    p.add_argument("--max-iter", type=int, default=3, help="闭环迭代上限")
    p.add_argument("--max-roll-step", type=float, default=10.0,
                   help="单次迭代 roll 修正限幅 (度)")
    p.add_argument("--max-y-step", type=float, default=50.0,
                   help="单次迭代 y 修正限幅 (mm)")
    # ---- 坐标映射 (安装方向相关, dry-run 核对后确定) ----
    p.add_argument("--roll-sign", type=float, default=None,
                   help="roll 修正符号 (+1/-1) (默认读 camera_config.yaml "
                        "fine_tune.roll_sign)")
    p.add_argument("--y-sign", type=float, default=None,
                   help="y 修正符号 (+1/-1) (默认读 camera_config.yaml fine_tune.y_sign)")
    p.add_argument("--z-sign", type=float, default=None,
                   help="深度进给符号 (+1/-1) (默认读 camera_config.yaml fine_tune.z_sign)")
    p.add_argument("--depth-axis", default="x", choices=["x", "y", "z"],
                   help="深度进给沿 tool 系哪个轴 (默认 x, 即相机视线/进刀方向)")
    p.add_argument("--y-axis", default="y", choices=["x", "y", "z"],
                   help="y 修正沿 tool 系哪个轴 (默认 y)")
    # ---- 运行模式 ----
    p.add_argument("--dry-run", action="store_true",
                   help="只计算增量并输出可视化, 不动臂")
    p.add_argument("--move-timeout", type=float, default=60.0,
                   help="move_pose 服务超时 (秒)")
    p.add_argument("--settle-frames", type=int, default=15,
                   help="每次取帧前丢弃的帧数 (等待稳定)")
    p.add_argument("--settle-time", type=float, default=0.6,
                   help="每次取帧前额外等待的时长 (秒), 确保取到移动后的新画面 "
                        "(默认 0.6)")
    return p.parse_args()


# ============ 相机取帧 (持久 Pipeline, 支持闭环多次取帧) ============

class CameraGrabber:
    """启动 color+depth 流并保持打开, grab() 每次 AlignFilter 对齐后取一帧。"""

    def __init__(self, camera_id: str, config_path: str):
        import yaml
        from pyorbbecsdk import (Context, Pipeline, Config, OBSensorType, OBFormat,
                                 OBFrameAggregateOutputMode, AlignFilter, OBStreamType)

        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        cam_cfg = next(c for c in cfg["cameras"] if c["id"] == camera_id)
        target_serial = cam_cfg["serial"]

        ctx = Context()
        dl = ctx.query_devices()
        device = None
        for i in range(dl.get_count()):
            d = dl.get_device_by_index(i)
            if d.get_device_info().get_serial_number() == target_serial:
                device = d
                break
        if device is None:
            raise RuntimeError(f"相机 {camera_id} (serial={target_serial}) 未连接")

        self._pipe = Pipeline(device)
        config = Config()
        try:
            cp = self._pipe.get_stream_profile_list(OBSensorType.COLOR_SENSOR) \
                .get_video_stream_profile(0, 0, OBFormat.RGB, 0)
        except Exception:
            cp = self._pipe.get_stream_profile_list(OBSensorType.COLOR_SENSOR) \
                .get_default_video_stream_profile()
        config.enable_stream(cp)
        try:
            dp = self._pipe.get_stream_profile_list(OBSensorType.DEPTH_SENSOR) \
                .get_video_stream_profile(0, 0, OBFormat.Y16, 0)
        except Exception:
            dp = self._pipe.get_stream_profile_list(OBSensorType.DEPTH_SENSOR) \
                .get_default_video_stream_profile()
        config.enable_stream(dp)
        try:
            config.set_frame_aggregate_output_mode(OBFrameAggregateOutputMode.FULL_FRAME_REQUIRE)
        except Exception:
            pass
        self._pipe.start(config)
        self._align = AlignFilter(align_to_stream=OBStreamType.COLOR_STREAM)
        print("[相机] pipeline started (depth->color 对齐)")

    def grab(self, settle_frames: int = 15, settle_sec: float = 0.6):
        """丢帧直到帧数和时长条件都满足, 返回 (color_bgr, depth_m)。

        帧数条件: 丢 settle_frames 帧; 时长条件: 距调用起 settle_sec 秒
        (保证取到的是调用时刻之后的新画面, 而非管线里缓存的旧帧)。
        """
        from test_grasp_single import _frame_to_bgr, _frame_to_depth_mm
        got = 0
        color = depth = None
        t0 = time.time()
        while time.time() - t0 < 10.0:
            fs = self._pipe.wait_for_frames(1000)
            if fs is None:
                continue
            try:
                aligned = self._align.process(fs)
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
                color = _frame_to_bgr(cf)
                depth = _frame_to_depth_mm(df)
                if color is not None and depth is not None:
                    got += 1
                    if got > settle_frames and time.time() - t0 >= settle_sec:
                        return color, depth
        raise RuntimeError("取帧失败 (AlignFilter depth->color)")

    def close(self):
        try:
            self._pipe.stop()
        except Exception:
            pass


# ============ 位姿数学 (与工作流 _apply_pose_offset 同一约定) ============

def rpy_to_R(r_deg: float, p_deg: float, y_deg: float) -> np.ndarray:
    """XYZ intrinsic RPY (度) -> 旋转矩阵。"""
    r, p, y = math.radians(r_deg), math.radians(p_deg), math.radians(y_deg)
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def R_to_quat(R: np.ndarray) -> tuple[float, float, float, float]:
    """旋转矩阵 -> 四元数 (x, y, z, w)。"""
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


def T_from_tq(t: np.ndarray, q: tuple) -> np.ndarray:
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


def tool_offset_T(droll_deg: float, t_tool_m: np.ndarray) -> np.ndarray:
    """tool 系增量 -> 4x4: 绕 tool x 旋转 droll + 平移 t_tool (米)。"""
    T = np.eye(4)
    T[:3, :3] = rpy_to_R(droll_deg, 0.0, 0.0)  # RPY roll = 绕 x
    T[:3, 3] = t_tool_m
    return T


# ============ ROS2: TF + /move_pose ============

class ArmInterface:
    """rclpy 节点: TF 查询 base_link->EE + MoveP 服务调用。

    后台线程 spin, 主线程 call_async + 轮询 future (同 mixed RosCaller 模式)。
    """

    def __init__(self, arm: str, move_timeout: float):
        import rclpy
        from rclpy.node import Node
        import tf2_ros
        from control_interfaces.srv import MoveP

        rclpy.init()
        self._rclpy = rclpy
        self.node = Node("fine_tune_grasp")
        self._tf_buffer = tf2_ros.Buffer()
        tf2_ros.TransformListener(self._tf_buffer, self.node)
        self._movep = self.node.create_client(MoveP, "move_pose")
        self._arm = arm
        self._letter = arm[0].upper()
        self.ee_link = f"ARM-{self._letter}-J7_Link"
        self._move_timeout = move_timeout
        self._spin_thread = threading.Thread(
            target=rclpy.spin, args=(self.node,), daemon=True)
        self._spin_thread.start()

    def get_T_base_ee(self, timeout: float = 2.0):
        """TF 查询 base_link->EE, 返回 4x4 (米) 或 None。"""
        from rclpy.duration import Duration
        try:
            msg = self._tf_buffer.lookup_transform(
                "base_link", self.ee_link, self._rclpy.time.Time(),
                timeout=Duration(seconds=timeout))
        except Exception as e:
            print(f"[TF] base_link->{self.ee_link} 查询失败: {e}")
            return None
        t = msg.transform.translation
        q = msg.transform.rotation
        return T_from_tq(np.array([t.x, t.y, t.z]),
                         (q.x, q.y, q.z, q.w))

    def move_p(self, T_base_target: np.ndarray) -> dict:
        """T_base_target (4x4, 米) -> /move_pose。返回 {success, message}。"""
        from geometry_msgs.msg import PoseStamped
        from control_interfaces.srv import MoveP

        if not self._movep.wait_for_service(timeout_sec=5.0):
            return {"success": False, "message": "move_pose 服务不可用"}
        req = MoveP.Request()
        req.lor = self._arm
        req.to_frame = self.ee_link
        req.reference_frame = "base_link"
        req.planner = "ompl"
        pose = PoseStamped()
        pose.header.frame_id = "base_link"
        t = T_base_target[:3, 3]
        qx, qy, qz, qw = R_to_quat(T_base_target[:3, :3])
        pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = \
            float(t[0]), float(t[1]), float(t[2])
        pose.pose.orientation.x, pose.pose.orientation.y = float(qx), float(qy)
        pose.pose.orientation.z, pose.pose.orientation.w = float(qz), float(qw)
        req.target_pose = pose

        future = self._movep.call_async(req)
        t0 = time.time()
        while not future.done() and time.time() - t0 < self._move_timeout:
            time.sleep(0.05)
        if not future.done():
            return {"success": False,
                    "message": f"move_pose 超时 ({self._move_timeout}s)"}
        try:
            resp = future.result()
        except Exception as e:
            return {"success": False, "message": f"move_pose 调用失败: {e}"}
        return {"success": bool(resp.success),
                "message": getattr(resp, "message", "") or ""}

    def wait_stationary(self, timeout: float = 5.0, still_sec: float = 0.4,
                        pos_tol: float = 0.001) -> bool:
        """轮询 TF 直到 EE 位置连续 still_sec 秒变化 < pos_tol (米)。

        move_pose 服务返回成功不代表运动已结束, 测量前必须确认臂真正停稳,
        否则取到的帧是运动中间状态。超时返回 False。
        """
        last = None
        stable_since = None
        t0 = time.time()
        while time.time() - t0 < timeout:
            T = self.get_T_base_ee(timeout=0.2)
            if T is None:
                stable_since = None
                continue
            p = T[:3, 3]
            if last is not None and np.linalg.norm(p - last) < pos_tol:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= still_sec:
                    return True
            else:
                stable_since = None
            last = p
            time.sleep(0.05)
        return False

    def shutdown(self):
        try:
            self.node.destroy_node()
        except Exception:
            pass
        try:
            self._rclpy.shutdown()
        except Exception:
            pass


# ============ 主流程 ============

def measure_once(grabber, detector, K, args, it, phase):
    """取一帧并完成检测/测量。返回 (color, depth, best, m) 或 None (致命错误)。"""
    color, depth = grabber.grab(args.settle_frames, args.settle_time)
    results = detector.detect(color)
    if not results:
        print(f"[错误] {phase}{it}: YOLO 未检测到取样杆")
        return None
    best = max(results, key=lambda r: r.mask_area_px)
    print(f"[{phase}{it}] YOLO conf={best.conf:.3f} mask={best.mask_area_px}px")
    m = measure(color, depth, best.mask, K)
    if m is None:
        print(f"[错误] {phase}{it}: mask 中轴线/深度计算失败")
        return None
    if abs(m["roll_err_deg"]) > MAX_ROLL_ERR_DEG:
        print(f"[错误] {phase}{it}: 杆轴与竖直夹角 {m['roll_err_deg']:.1f}° "
              f"超过 {MAX_ROLL_ERR_DEG}°, 疑似误识别, 中止")
        return None
    return color, depth, best, m


def main():
    args = parse_args()
    if args.out is None:
        args.out = new_out_prefix()
    Ks, _, _ = load_intrinsics(args.config, args.camera)
    ft = load_fine_tune_cfg(args.config, args.camera)
    if args.cam_y_offset is None:
        args.cam_y_offset = ft["cam_y_offset_mm"]
        print(f"[配置] {args.camera}: cam_y_offset={args.cam_y_offset:+.1f}mm "
              f"(camera_config.yaml)")
    if args.depth_offset is None:
        args.depth_offset = ft["depth_offset_mm"]
        print(f"[配置] {args.camera}: depth_offset={args.depth_offset:+.1f}mm "
              f"(camera_config.yaml)")
    for name in ("roll_sign", "y_sign", "z_sign"):
        if getattr(args, name) is None:
            setattr(args, name, ft[name])
            print(f"[配置] {args.camera}: {name}={ft[name]:+.0f} (camera_config.yaml)")
    K = Ks["color"]

    detector = YOLODetector(args.model, names=[n.strip() for n in args.names.split(",")],
                            conf=args.conf, iou=0.45, imgsz=640, device="cpu")

    grabber = CameraGrabber(args.camera, args.config)
    arm = ArmInterface(args.arm, args.move_timeout)
    exit_code = 0

    def move_tool(droll_deg: float, t_tool_m: np.ndarray, phase: str, it) -> bool:
        """下发一次 tool 系增量 (droll + 平移)。返回是否成功。"""
        T_base_ee = arm.get_T_base_ee()
        if T_base_ee is None:
            print("[错误] 无法获取当前 EE 位姿, 中止")
            return False
        T_target = T_base_ee @ tool_offset_T(droll_deg, t_tool_m)
        print(f"[{phase}{it}] move_p: droll={droll_deg:+.2f}° t_tool={t_tool_m * 1000}mm")
        r = arm.move_p(T_target)
        if not r["success"]:
            print(f"[错误] {phase}{it}: move_pose 失败: {r['message']}")
            return False
        # move_pose 返回成功不代表已停稳, 等 EE 静止后再进入下一次测量
        if not arm.wait_stationary():
            print(f"[警告] {phase}{it}: 等待臂静止超时, 画面可能是运动中间状态")
        return True

    try:
        # 启动时等臂停稳 (预抓取位可能刚到位就开始测量)
        if not arm.wait_stationary():
            print("[警告] 启动时等待臂静止超时, 首帧可能未稳定")
        if args.dry_run:
            # ---- dry-run: 单帧测量, 打印三个阶段的拟修正量 ----
            res = measure_once(grabber, detector, K, args, 1, "迭代")
            if res is None:
                exit_code = 1
            else:
                color, depth, best, m = res
                dy_eff = m["dy_mm"] - args.cam_y_offset
                dz_mm = (m["depth_med"] - args.ref_depth) * 1000.0 + args.depth_offset
                print(f"[dry-run] roll={m['roll_err_deg']:+.2f}°  "
                      f"dy测量={m['dy_mm']:+.1f}mm 镜头偏移={args.cam_y_offset:+.1f}mm "
                      f"dy有效={dy_eff:+.1f}mm ({m['dy_px']:+.1f}px)  "
                      f"depth={m['depth_med']*1000:.0f}mm  dz={dz_mm:+.1f}mm")
                draw_viz(color, depth, best.mask, m,
                         f"{args.out}_dryrun.jpg", "dry-run (dy 为转正前估计)")
                droll = float(np.clip(args.roll_sign * m["roll_err_deg"],
                                      -args.max_roll_step, args.max_roll_step))
                dy = float(np.clip(args.y_sign * dy_eff,
                                   -args.max_y_step, args.max_y_step))
                print(f"[dry-run] 阶段1 拟转正: droll(x)={droll:+.2f}°")
                print(f"[dry-run] 阶段2 拟修正 dy({args.y_axis})={dy:+.1f}mm "
                      f"(真跑时转正后重新测量)")
                dz = args.z_sign * dz_mm
                print(f"[dry-run] 阶段3 深度进给: dz({args.depth_axis})={dz:+.1f}mm "
                      f"(测量={m['depth_med']*1000:.0f}mm 参考={args.ref_depth*1000:.0f}mm "
                      f"深度偏移={args.depth_offset:+.1f}mm, "
                      f"容差±{args.depth_tol*1000:.0f}mm)")
                if abs(dz_mm) > args.depth_tol * 1000.0:
                    print("[dry-run] 警告: 超出深度容差, 真跑时会报错拒动")
        else:
            # ---- 阶段1: roll 对齐 (先转正, 再测 y) ----
            m = None
            for it in range(1, args.max_iter + 1):
                res = measure_once(grabber, detector, K, args, it, "roll迭代")
                if res is None:
                    exit_code = 1
                    break
                color, depth, best, m = res
                print(f"[roll迭代{it}] roll={m['roll_err_deg']:+.2f}°  "
                      f"depth={m['depth_med']*1000:.0f}mm")
                if abs(m["roll_err_deg"]) < args.roll_tol:
                    print(f"[roll迭代{it}] roll 收敛 (<±{args.roll_tol}°)")
                    break
                droll = float(np.clip(args.roll_sign * m["roll_err_deg"],
                                      -args.max_roll_step, args.max_roll_step))
                draw_viz(color, depth, best.mask, m,
                         f"{args.out}_roll{it}.jpg", f"roll{it}: correct roll")
                if not move_tool(droll, np.zeros(3), "roll迭代", it):
                    exit_code = 1
                    break
            else:
                print(f"[警告] 阶段1 达到最大迭代次数 {args.max_iter}, roll 未完全收敛")

            # ---- 阶段2: y 对齐 (roll 转正后测量, 扣除镜头横向偏移) ----
            if exit_code == 0:
                for it in range(1, args.max_iter + 1):
                    res = measure_once(grabber, detector, K, args, it, "y迭代")
                    if res is None:
                        exit_code = 1
                        break
                    color, depth, best, m = res
                    dy_eff = m["dy_mm"] - args.cam_y_offset
                    print(f"[y迭代{it}] roll={m['roll_err_deg']:+.2f}°  "
                          f"dy测量={m['dy_mm']:+.1f}mm ({m['dy_px']:+.1f}px)  "
                          f"镜头偏移={args.cam_y_offset:+.1f}mm  "
                          f"dy有效={dy_eff:+.1f}mm  depth={m['depth_med']*1000:.0f}mm")
                    roll_ok = abs(m["roll_err_deg"]) < args.roll_tol
                    y_ok = abs(dy_eff) < args.y_tol
                    if roll_ok and y_ok:
                        print(f"[y迭代{it}] 二次对齐收敛 "
                              f"(roll<±{args.roll_tol}°, |dy|<{args.y_tol}mm)")
                        break
                    if not roll_ok:
                        # roll 漂移, 先转正再测 y
                        droll = float(np.clip(args.roll_sign * m["roll_err_deg"],
                                              -args.max_roll_step, args.max_roll_step))
                        draw_viz(color, depth, best.mask, m,
                                 f"{args.out}_y{it}.jpg", f"y{it}: roll drifted")
                        if not move_tool(droll, np.zeros(3), "y迭代", it):
                            exit_code = 1
                            break
                        continue
                    dy = float(np.clip(args.y_sign * dy_eff,
                                       -args.max_y_step, args.max_y_step))
                    t_tool = np.zeros(3)
                    t_tool["xyz".index(args.y_axis)] += dy / 1000.0
                    draw_viz(color, depth, best.mask, m,
                             f"{args.out}_y{it}.jpg", f"y{it}: correct dy")
                    if not move_tool(0.0, t_tool, "y迭代", it):
                        exit_code = 1
                        break
                else:
                    print(f"[警告] 阶段2 达到最大迭代次数 {args.max_iter}, y 未完全收敛")

            # ---- 阶段3: 深度进给 (二次对齐后执行一次, 含镜头深度偏移) ----
            if exit_code == 0 and m is not None:
                dz_mm = (m["depth_med"] - args.ref_depth) * 1000.0 + args.depth_offset
                if abs(dz_mm) > args.depth_tol * 1000.0:
                    print(f"[错误] 深度增量 {dz_mm:+.1f}mm 超出容差 "
                          f"±{args.depth_tol*1000:.0f}mm, 拒绝进给 (测量="
                          f"{m['depth_med']*1000:.0f}mm 参考={args.ref_depth*1000:.0f}mm "
                          f"深度偏移={args.depth_offset:+.1f}mm)")
                    exit_code = 1
                elif abs(dz_mm) < 1.0:
                    print(f"[深度] 增量 {dz_mm:+.1f}mm < 1mm, 无需进给")
                else:
                    dz = args.z_sign * dz_mm
                    t_tool = np.zeros(3)
                    t_tool["xyz".index(args.depth_axis)] += dz / 1000.0
                    print(f"[深度] 进给: dz({args.depth_axis})={dz:+.1f}mm "
                          f"(测量={m['depth_med']*1000:.0f}mm "
                          f"参考={args.ref_depth*1000:.0f}mm "
                          f"深度偏移={args.depth_offset:+.1f}mm)")
                    if not move_tool(0.0, t_tool, "深度", 0):
                        exit_code = 1

        if exit_code == 0:
            print("[完成] 微调段结束")
    finally:
        grabber.close()
        arm.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

"""取样杆三阶段闭环微调 (工作流 mixed 功能)。

前提: 臂已通过 QR 标定移动到预抓取位 (本功能不做 QR 定位, 不做闭爪)。
流程与 test_fine_tune_grasp.py 一致, 基础设施换成 mixed ctx:
  测量   ctx.ros_call("/camera/fine_tune_measure")   (相机管理节点, 不直连相机)
  运动   ctx.ros_call_typed("/move_pose", MoveP)     (tool 系增量经 T_base_ee@T_offset)
  停稳   ctx.tf_lookup 轮询 (move_pose 返回成功不代表已停稳)
  阶段3 深度进给使用阶段2 最后一次测量的 depth_med (与脚本一致)。

深度/y 修正沿 tool 系固定轴 (x=进刀方向, y=横向), 方向由 camera_config.yaml
的 fine_tune 符号配置决定 (随测量结果返回), 不做参数化。
"""
import logging
import math
import time

import numpy as np

from ..registry import mixed_function

logger = logging.getLogger("mixed_execution.functions.fine_tune_grasp")

EE_LINK = {"left": "ARM-L-J7_Link", "right": "ARM-R-J7_Link"}
MOVE_TIMEOUT = 60.0        # move_pose 服务超时 (秒)
MEASURE_TIMEOUT = 30.0     # 测量服务超时 (秒, 含 settle ~2s)
MAX_ROLL_STEP_DEG = 10.0   # 单次迭代 roll 修正限幅 (度)
MAX_Y_STEP_MM = 50.0       # 单次迭代 y 修正限幅 (mm)
SETTLE_FRAMES = 15         # 每次取帧前丢弃的帧数
SETTLE_SEC = 0.6           # 每次取帧前额外等待 (秒)
STILL_TOL_M = 0.001        # 停稳判定位置容差
STILL_SEC = 0.4            # 停稳判定持续时长


class FineTuneError(Exception):
    """微调失败 (测量失败 / 运动失败 / 深度超容差拒动 / 参数缺失)。"""


# ---- 位姿数学 (与 workflow 上肢 tool 偏移同一约定) ----

def _rpy_to_R(r_deg: float, p_deg: float, y_deg: float) -> np.ndarray:
    r, p, y = math.radians(r_deg), math.radians(p_deg), math.radians(y_deg)
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def _R_to_quat(R: np.ndarray) -> tuple[float, float, float, float]:
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


def _T_from_tq(t: np.ndarray, q) -> np.ndarray:
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


def _tool_offset_T(droll_deg: float, t_tool_m: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = _rpy_to_R(droll_deg, 0.0, 0.0)  # RPY roll = 绕 tool x
    T[:3, 3] = t_tool_m
    return T


# ---- 基础设施封装 (ctx) ----

def _get_T_base_ee(ctx, ee_link: str) -> np.ndarray:
    res = ctx.tf_lookup("base_link", ee_link)
    if res is None:
        raise FineTuneError(f"无法获取 TF base_link->{ee_link}")
    return _T_from_tq(res[0], res[1])


def _move_p(ctx, arm: str, ee_link: str, T_base_target: np.ndarray) -> None:
    from control_interfaces.srv import MoveP
    from geometry_msgs.msg import PoseStamped
    req = MoveP.Request()
    req.lor = arm
    req.to_frame = ee_link
    req.reference_frame = "base_link"
    req.planner = "ompl"
    pose = PoseStamped()
    pose.header.frame_id = "base_link"
    t = T_base_target[:3, 3]
    qx, qy, qz, qw = _R_to_quat(T_base_target[:3, :3])
    pose.pose.position.x, pose.pose.position.y, pose.pose.position.z = \
        float(t[0]), float(t[1]), float(t[2])
    pose.pose.orientation.x, pose.pose.orientation.y = float(qx), float(qy)
    pose.pose.orientation.z, pose.pose.orientation.w = float(qz), float(qw)
    req.target_pose = pose
    resp = ctx.ros_call_typed("/move_pose", MoveP, req, timeout=MOVE_TIMEOUT)
    if resp is None:
        raise FineTuneError("move_pose 服务调用失败/超时")
    if not getattr(resp, "success", False):
        raise FineTuneError(f"move_pose 失败: {getattr(resp, 'message', '')}")


def _wait_stationary(ctx, ee_link: str, timeout: float = 5.0) -> bool:
    """轮询 TF 直到 EE 位置连续 STILL_SEC 秒变化 < STILL_TOL_M。超时返回 False。"""
    last = None
    stable_since = None
    t0 = time.time()
    while time.time() - t0 < timeout:
        ctx.check_cancel()
        res = ctx.tf_lookup("base_link", ee_link, timeout=0.2)
        if res is None:
            stable_since = None
            continue
        p = res[0]
        if last is not None and np.linalg.norm(p - last) < STILL_TOL_M:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= STILL_SEC:
                return True
        else:
            stable_since = None
        last = p
        time.sleep(0.05)
    return False


# ---- 混合功能 ----

@mixed_function(
    name="fine_tune_grasp",
    description="取样杆三阶段闭环微调 (roll对齐→y对齐→深度进给), "
                "前提: 臂已在预抓取位; 不做 QR 定位和闭爪",
    params_schema=[
        {"name": "camera", "type": "string",
         "description": "相机 ID (right_arm/left_arm)",
         "default": "right_arm", "required": False},
        {"name": "arm", "type": "select", "description": "手臂",
         "options": ["left", "right"], "default": "right", "required": False},
        {"name": "ref_depth", "type": "number",
         "description": "参考深度 (米), 与预抓取位姿绑定, 手动标定",
         "default": None, "required": True},
        {"name": "max_iter", "type": "number", "description": "每阶段闭环迭代上限",
         "default": 3, "required": False},
        {"name": "roll_tol", "type": "number", "description": "roll 收敛阈值 (度)",
         "default": 1.0, "required": False},
        {"name": "y_tol", "type": "number", "description": "y 收敛阈值 (mm)",
         "default": 2.0, "required": False},
        {"name": "depth_tol", "type": "number",
         "description": "深度增量容差 (米), 超出拒动",
         "default": 0.030, "required": False},
        {"name": "dry_run", "type": "bool",
         "description": "只测量并计算拟修正量, 不动臂",
         "default": False, "required": False},
    ],
    moves_base=False,
)
def fine_tune_grasp(ctx, camera: str = "right_arm", arm: str = "right",
                    ref_depth: float = None, max_iter: int = 3,
                    roll_tol: float = 1.0, y_tol: float = 2.0,
                    depth_tol: float = 0.030, dry_run: bool = False):
    """取样杆三阶段闭环微调。"""
    if ref_depth is None:
        raise FineTuneError("参数 ref_depth 必填 (参考深度, 米, 与预抓取位绑定)")
    if arm not in EE_LINK:
        raise FineTuneError(f"未知手臂: {arm} (可选 {list(EE_LINK)})")
    if max_iter is None or int(max_iter) < 1:
        raise FineTuneError(f"max_iter 必须为 >= 1 的整数 (当前: {max_iter})")
    if roll_tol is None or roll_tol <= 0 or y_tol is None or y_tol <= 0 \
            or depth_tol is None or depth_tol <= 0:
        raise FineTuneError(
            f"容差参数必须为正数 (roll_tol={roll_tol}, y_tol={y_tol}, depth_tol={depth_tol})")
    ee_link = EE_LINK[arm]
    viz_paths: list[str] = []
    iters = {"roll": 0, "y": 0}

    def measure_once() -> dict:
        r = ctx.ros_call("/camera/fine_tune_measure",
                         {"camera_id": camera, "settle_frames": SETTLE_FRAMES,
                          "settle_sec": SETTLE_SEC},
                         timeout=MEASURE_TIMEOUT)
        if not r.get("success"):
            raise FineTuneError(f"测量失败: {r.get('message', '')}")
        d = r["data"]
        if d.get("viz_path"):
            viz_paths.append(d["viz_path"])
        return d

    def move_tool(droll_deg: float, t_tool_m: np.ndarray) -> None:
        T_base_ee = _get_T_base_ee(ctx, ee_link)
        _move_p(ctx, arm, ee_link, T_base_ee @ _tool_offset_T(droll_deg, t_tool_m))
        if not _wait_stationary(ctx, ee_link):
            logger.warning("等待臂静止超时, 画面可能是运动中间状态")

    # ---- dry-run: 单帧测量, 只算不动 ----
    if dry_run:
        d = measure_once()
        ft = d["fine_tune"]
        dy_eff = d["dy_mm"] - ft["cam_y_offset_mm"]
        dz_mm = (d["depth_med"] - ref_depth) * 1000.0 + ft["depth_offset_mm"]
        planned = {
            "droll_deg": float(np.clip(ft["roll_sign"] * d["roll_err_deg"],
                                       -MAX_ROLL_STEP_DEG, MAX_ROLL_STEP_DEG)),
            "dy_mm": float(np.clip(ft["y_sign"] * dy_eff,
                                   -MAX_Y_STEP_MM, MAX_Y_STEP_MM)),
            "dz_mm": ft["z_sign"] * dz_mm,
            "depth_out_of_tolerance": bool(abs(dz_mm) > depth_tol * 1000.0),
        }
        ctx.set_progress(100.0, "dry-run 完成")
        return {"converged": True, "iterations": {"roll": 1, "y": 0},
                "planned": planned, "viz_paths": viz_paths}

    # ---- 阶段1: roll 对齐 (先转正再测 y, 避免倾斜时 dy 被杠杆臂污染) ----
    roll_converged = False
    for it in range(1, max_iter + 1):
        ctx.check_cancel()
        iters["roll"] = it
        d = measure_once()
        ctx.set_progress(10.0 * it, f"阶段1 roll迭代{it}: roll={d['roll_err_deg']:+.2f}°")
        if abs(d["roll_err_deg"]) < roll_tol:
            roll_converged = True
            break
        droll = float(np.clip(d["fine_tune"]["roll_sign"] * d["roll_err_deg"],
                              -MAX_ROLL_STEP_DEG, MAX_ROLL_STEP_DEG))
        move_tool(droll, np.zeros(3))
    if not roll_converged:
        logger.warning("阶段1 达到最大迭代 %d, roll 未完全收敛", max_iter)

    # ---- 阶段2: y 对齐 (扣除镜头横向偏移; roll 漂移则先转正) ----
    y_converged = False
    m = d
    for it in range(1, max_iter + 1):
        ctx.check_cancel()
        iters["y"] = it
        d = measure_once()
        m = d
        ft = d["fine_tune"]
        dy_eff = d["dy_mm"] - ft["cam_y_offset_mm"]
        ctx.set_progress(40.0 + 10.0 * it,
                         f"阶段2 y迭代{it}: dy有效={dy_eff:+.1f}mm")
        roll_ok = abs(d["roll_err_deg"]) < roll_tol
        if roll_ok and abs(dy_eff) < y_tol:
            y_converged = True
            break
        if not roll_ok:
            droll = float(np.clip(ft["roll_sign"] * d["roll_err_deg"],
                                  -MAX_ROLL_STEP_DEG, MAX_ROLL_STEP_DEG))
            move_tool(droll, np.zeros(3))
            continue
        dy = float(np.clip(ft["y_sign"] * dy_eff, -MAX_Y_STEP_MM, MAX_Y_STEP_MM))
        t_tool = np.zeros(3)
        t_tool[1] += dy / 1000.0  # tool y
        move_tool(0.0, t_tool)
    if not y_converged:
        logger.warning("阶段2 达到最大迭代 %d, y 未完全收敛", max_iter)

    # ---- 阶段3: 深度进给 (用阶段2 最后一次测量, 一次执行) ----
    # 阶段2 末帧 roll 未收敛时重测一次 (倾斜杆的深度测量不可靠); 仍超限则中止
    if abs(m["roll_err_deg"]) >= roll_tol:
        m = measure_once()
        ctx.set_progress(87.0, f"阶段3 前重测: roll={m['roll_err_deg']:+.2f}°")
        if abs(m["roll_err_deg"]) >= roll_tol:
            raise FineTuneError(
                f"深度进给中止: 杆轴 roll {m['roll_err_deg']:+.1f}° 未收敛 "
                f"(阈值 ±{roll_tol}°), 倾斜杆的深度测量不可靠")
    ft = m["fine_tune"]
    dz_mm = (m["depth_med"] - ref_depth) * 1000.0 + ft["depth_offset_mm"]
    ctx.set_progress(85.0, f"阶段3 深度: dz={dz_mm:+.1f}mm")
    if abs(dz_mm) > depth_tol * 1000.0:
        raise FineTuneError(
            f"深度增量 {dz_mm:+.1f}mm 超出容差 ±{depth_tol * 1000:.0f}mm, "
            f"拒绝进给 (测量={m['depth_med'] * 1000:.0f}mm "
            f"参考={ref_depth * 1000:.0f}mm 偏移={ft['depth_offset_mm']:+.1f}mm)")
    if abs(dz_mm) >= 1.0:
        t_tool = np.zeros(3)
        t_tool[0] += ft["z_sign"] * dz_mm / 1000.0  # tool x = 进刀方向
        move_tool(0.0, t_tool)

    converged = roll_converged and y_converged
    ctx.set_progress(100.0, "微调完成" + ("" if converged else " (未完全收敛)"))
    return {
        "converged": converged,
        "iterations": iters,
        "final": {
            "roll_err_deg": m["roll_err_deg"],
            "dy_eff_mm": m["dy_mm"] - ft["cam_y_offset_mm"],
            "dz_mm": dz_mm,
        },
        "viz_paths": viz_paths,
    }

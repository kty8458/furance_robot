"""fine_tune_grasp 闭环状态机测试 (mock ctx, 无 ROS 服务/相机/臂)。"""
import numpy as np
import pytest
from types import SimpleNamespace

from mixed_execution.executor import MixedCancelled
from mixed_execution.functions.fine_tune_grasp import (
    fine_tune_grasp, FineTuneError, _R_to_quat, _rpy_to_R,
)

FT = {"cam_y_offset_mm": 2.0, "depth_offset_mm": 0.0,
      "roll_sign": 1.0, "y_sign": 1.0, "z_sign": 1.0}


def m_data(roll=0.1, dy_mm=1.0, depth=0.50):
    """一次测量的服务返回 data。"""
    return {"roll_err_deg": roll, "dy_px": 5.0, "dy_mm": dy_mm,
            "depth_med": depth, "conf": 0.9, "mask_area_px": 5000,
            "viz_path": "", "fine_tune": dict(FT)}


class FakeCtx:
    """按预置序列回放测量结果; 记录 move 请求; TF 恒为单位位姿。"""

    def __init__(self, measures):
        self.measures = list(measures)
        self.moves = []          # 记录 MoveP.Request
        self.cancelled = False
        self.progress = []

    def ros_call(self, service, params, timeout=None):
        assert service == "/camera/fine_tune_measure"
        assert len(self.measures) > 0, "测量次数超出预置序列"
        return {"success": True, "message": "OK", "data": self.measures.pop(0)}

    def ros_call_typed(self, service, srv_type, request, timeout=None):
        assert service == "/move_pose"
        self.moves.append(request)
        return SimpleNamespace(success=True, message="")

    def tf_lookup(self, parent, child, timeout=2.0):
        return (np.zeros(3), np.array([0.0, 0.0, 0.0, 1.0]))  # 单位位姿

    def set_progress(self, pct, message=""):
        self.progress.append((pct, message))

    def check_cancel(self):
        if self.cancelled:
            raise MixedCancelled("Cancelled by user")


def test_all_converged_no_move():
    ctx = FakeCtx([m_data(roll=0.2, dy_mm=2.5),   # 阶段1: 已收敛 (dy 不看)
                   m_data(roll=0.1, dy_mm=2.5)])  # 阶段2: dy_eff=0.5 < y_tol 收敛
    r = fine_tune_grasp(ctx, camera="right_arm", arm="right", ref_depth=0.50)
    assert r["converged"] is True
    assert r["iterations"] == {"roll": 1, "y": 1}
    assert len(ctx.moves) == 0  # 深度 dz=0 < 1mm 也跳过


def test_roll_correction_then_converge():
    ctx = FakeCtx([m_data(roll=5.0), m_data(roll=0.2), m_data(roll=0.1, dy_mm=2.5)])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is True
    assert len(ctx.moves) == 1
    # 验证运动请求: 绕 tool x 转 +5° (roll_sign=1, TF 单位位姿)
    req = ctx.moves[0]
    assert req.lor == "right" and req.to_frame == "ARM-R-J7_Link"
    qx, qy, qz, qw = _R_to_quat(_rpy_to_R(5.0, 0.0, 0.0))
    p = req.target_pose.pose
    assert abs(p.orientation.x - qx) < 1e-6
    assert abs(p.orientation.z - qz) < 1e-6
    assert abs(p.orientation.w - qw) < 1e-6
    assert abs(p.position.x) < 1e-9 and abs(p.position.y) < 1e-9


def test_y_correction():
    # 阶段1 收敛; 阶段2 dy_mm=10, 扣 cam_y_offset=2 -> dy_eff=8 -> 修 8mm 后收敛
    ctx = FakeCtx([m_data(roll=0.1),
                   m_data(roll=0.1, dy_mm=10.0),
                   m_data(roll=0.1, dy_mm=2.5)])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is True
    assert len(ctx.moves) == 1
    p = ctx.moves[0].target_pose.pose
    assert abs(p.position.y - 0.008) < 1e-9  # +8mm 沿 tool y
    assert abs(p.position.x) < 1e-9


def test_roll_drift_in_y_phase():
    # 阶段2 首次测量 roll 漂移到 4° -> 先转正再测 y
    ctx = FakeCtx([m_data(roll=0.1),
                   m_data(roll=4.0, dy_mm=10.0),   # roll 漂移
                   m_data(roll=0.1, dy_mm=2.5)])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is True
    assert len(ctx.moves) == 1  # 只有 roll 转正那一步
    p = ctx.moves[0].target_pose.pose
    assert abs(p.position.y) < 1e-9  # 是 roll 修正不是 y 修正


def test_depth_feed():
    # 阶段2 收敛 (depth=0.52): dz = (0.52-0.50)*1000 + 0 = 20mm < 容差 30mm -> 进给
    ctx = FakeCtx([m_data(roll=0.1), m_data(roll=0.1, dy_mm=2.5, depth=0.52)])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is True
    assert len(ctx.moves) == 1
    p = ctx.moves[0].target_pose.pose
    assert abs(p.position.x - 0.020) < 1e-9  # z_sign=1 沿 tool x +20mm


def test_depth_out_of_tolerance_rejects():
    # dz = 50mm > 容差 30mm -> 拒动失败
    ctx = FakeCtx([m_data(roll=0.1), m_data(roll=0.1, dy_mm=2.5, depth=0.55)])
    with pytest.raises(FineTuneError, match="拒绝"):
        fine_tune_grasp(ctx, ref_depth=0.50)
    assert len(ctx.moves) == 0


def test_max_iter_not_converged_warns_but_succeeds():
    # y 永不收敛 -> 3 次修正后警告返回, converged=False; 阶段3 再进给一次
    ctx = FakeCtx([m_data(roll=0.1)]
                  + [m_data(roll=0.1, dy_mm=10.0)] * 3)
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is False
    assert r["iterations"] == {"roll": 1, "y": 3}
    assert len(ctx.moves) == 3  # 3 次 y 修正


def test_measure_failure_raises():
    class FailCtx(FakeCtx):
        def ros_call(self, service, params, timeout=None):
            return {"success": False, "message": "YOLO 未检测到取样杆", "data": {}}
    with pytest.raises(FineTuneError, match="YOLO 未检测到"):
        fine_tune_grasp(FailCtx([]), ref_depth=0.50)


def test_cancel_midway():
    ctx = FakeCtx([m_data(roll=5.0)] * 10)
    ctx.cancelled = True
    with pytest.raises(MixedCancelled):
        fine_tune_grasp(ctx, ref_depth=0.50)


def test_dry_run_no_move():
    ctx = FakeCtx([m_data(roll=5.0, dy_mm=10.0, depth=0.52)])
    r = fine_tune_grasp(ctx, ref_depth=0.50, dry_run=True)
    assert len(ctx.moves) == 0
    assert abs(r["planned"]["droll_deg"] - 5.0) < 1e-9
    assert abs(r["planned"]["dy_mm"] - 8.0) < 1e-9
    assert abs(r["planned"]["dz_mm"] - 20.0) < 1e-9


def test_ref_depth_required():
    with pytest.raises(FineTuneError, match="ref_depth"):
        fine_tune_grasp(FakeCtx([]))


def test_max_iter_invalid():
    with pytest.raises(FineTuneError, match="max_iter"):
        fine_tune_grasp(FakeCtx([]), ref_depth=0.50, max_iter=0)


def test_phase3_remeasure_when_roll_drifted():
    # 阶段1 收敛 (roll=0.1); 阶段2 三次测量: 两次y修正后末帧roll漂移到4°, 触发roll修正;
    # 阶段3 前重测一次 roll收敛且depth=0.52 → 深度进给一次
    # moves: 2 y + 1 roll + 1 深度 = 4 次
    ctx = FakeCtx([
        m_data(roll=0.1),                          # 阶段1: 收敛
        m_data(roll=0.1, dy_mm=10.0),              # 阶段2 it=1: y修正
        m_data(roll=0.1, dy_mm=10.0),              # 阶段2 it=2: y修正
        m_data(roll=4.0, dy_mm=10.0),              # 阶段2 it=3: roll漂移, roll修正
        m_data(roll=0.1, dy_mm=2.5, depth=0.52),   # 阶段3 重测: roll收敛, depth=0.52
    ])
    r = fine_tune_grasp(ctx, ref_depth=0.50)
    assert r["converged"] is False   # y 未收敛
    assert len(ctx.moves) == 4
    # 最后一次 move 是深度进给: tool x += 20mm
    p = ctx.moves[-1].target_pose.pose
    assert abs(p.position.x - 0.020) < 1e-9


def test_phase3_abort_when_roll_still_bad():
    # 阶段2 末帧 roll=4°; 阶段3 重测 roll 仍 4° → 中止, 深度 move 未发生
    ctx = FakeCtx([
        m_data(roll=0.1),                          # 阶段1: 收敛
        m_data(roll=0.1, dy_mm=10.0),              # 阶段2 it=1: y修正
        m_data(roll=0.1, dy_mm=10.0),              # 阶段2 it=2: y修正
        m_data(roll=4.0, dy_mm=10.0),              # 阶段2 it=3: roll漂移, roll修正
        m_data(roll=4.0, dy_mm=10.0, depth=0.52),  # 阶段3 重测: roll仍超限
    ])
    with pytest.raises(FineTuneError, match="深度进给中止"):
        fine_tune_grasp(ctx, ref_depth=0.50)
    assert len(ctx.moves) == 3   # 只有阶段2 的 2y + 1roll, 无深度进给


def test_tolerance_must_be_positive():
    with pytest.raises(FineTuneError, match="容差参数"):
        fine_tune_grasp(FakeCtx([]), ref_depth=0.50, roll_tol=0)

"""混合功能测试样例: 全链路验证。

覆盖点:
  - 全部参数类型: string / number / bool / select (前端动态表单渲染)
  - ctx.ros_call 跨线程 ROS 服务调用 (/camera/list 只读查询)
  - ctx.chassis 底盘 HTTP 调用 (chassis_rotate 模式, 默认 dry_run 不动作)
  - ctx.set_progress 进度上报 / ctx.check_cancel 取消响应
  - 返回结果回传 (/mixed/status 的 result 字段)

默认 mode=dry_run, 不产生任何硬件动作, 可随时在工作流中运行验证链路。
"""

import logging

from ..registry import mixed_function

logger = logging.getLogger("mixed_execution.functions.test_sample")


@mixed_function(
    name="test_full_chain",
    description="测试样例: 全参数类型 + ROS 服务调用 + 可选底盘旋转 + 进度/取消, 默认空跑不动硬件",
    params_schema=[
        {"name": "label", "type": "string", "description": "任务标签 (仅用于日志展示)",
         "default": "test-01", "required": False},
        {"name": "mode", "type": "select", "description": "执行模式 (dry_run=空跑, chassis_rotate=真实底盘旋转)",
         "options": ["dry_run", "chassis_rotate"], "default": "dry_run", "required": False},
        {"name": "rotate_angle", "type": "number", "description": "chassis_rotate 模式的旋转角度 (度, 负值反转)",
         "default": 15.0, "required": False},
        {"name": "check_camera", "type": "bool", "description": "调用 /camera/list 验证 ROS 服务链路",
         "default": True, "required": False},
        {"name": "steps", "type": "number", "description": "模拟步数 (每步 1 秒, 可中途取消)",
         "default": 3, "required": False},
    ],
    moves_base=True,  # chassis_rotate 模式会移动底盘, 工作流预检按最保守声明
)
def test_full_chain(ctx, label: str = "test-01", mode: str = "dry_run",
                    rotate_angle: float = 15.0, check_camera: bool = True,
                    steps: int = 3):
    """混合执行链路测试: 参数 -> ROS 查询 -> 模拟步进 -> (可选) 底盘旋转。"""
    summary = {"label": label, "mode": mode, "steps": steps,
               "camera_check": None, "chassis": None}

    # 1) 参数回显
    ctx.set_progress(5.0, f"开始 [{label}] mode={mode}")
    logger.info("test_full_chain params: %s", ctx.params)

    # 2) ROS 服务链路验证 (/camera/list 只读, 服务不在线时记录并继续)
    if check_camera:
        ctx.set_progress(15.0, "调用 /camera/list")
        try:
            r = ctx.ros_call("/camera/list", {}) if ctx.ros_call else \
                {"success": False, "message": "ros_call not available"}
            summary["camera_check"] = {
                "success": bool(r.get("success")),
                "message": r.get("message", ""),
            }
        except Exception as e:
            summary["camera_check"] = {"success": False, "message": str(e)}
        ctx.set_progress(25.0, f"相机查询: {summary['camera_check']['message']}")

    # 3) 模拟步进 (验证进度 + 取消响应)
    steps = max(1, int(steps))
    for i in range(steps):
        ctx.check_cancel()
        ctx.set_progress(25.0 + (i / steps) * 50.0, f"模拟步骤 {i + 1}/{steps}")
        ctx.sleep(1.0)

    # 4) 底盘旋转 (chassis_rotate 模式才真实动作)
    if mode == "chassis_rotate":
        ctx.check_cancel()
        ctx.set_progress(80.0, f"底盘旋转 {rotate_angle}°")
        try:
            ctx.chassis.rotate(float(rotate_angle))
            summary["chassis"] = {"success": True, "angle": float(rotate_angle)}
        except Exception as e:
            summary["chassis"] = {"success": False, "message": str(e)}
            raise
    else:
        summary["chassis"] = {"success": True, "skipped": "dry_run"}

    ctx.set_progress(100.0, "完成")
    return summary

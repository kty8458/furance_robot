"""无硬件 demo 混合功能: 验证 /mixed/execute、/mixed/status、取消全链路。"""

import logging
import time

from ..registry import mixed_function

logger = logging.getLogger("mixed_execution.functions.demo")


@mixed_function(
    name="demo_progress",
    description="演示脚本: 分步执行并上报进度 (无硬件动作), 用于验证混合执行链路",
    params_schema=[
        {"name": "steps", "type": "number", "description": "执行步数",
         "default": 5, "required": False},
        {"name": "interval", "type": "number", "description": "每步间隔 (秒)",
         "default": 1.0, "required": False},
    ],
    moves_base=False,
)
def demo_progress(ctx, steps: int = 5, interval: float = 1.0):
    """分步 sleep + 进度上报, 演示取消响应。"""
    steps = max(1, int(steps))
    for i in range(steps):
        ctx.check_cancel()
        ctx.set_progress((i / steps) * 100.0, f"步骤 {i + 1}/{steps}")
        ctx.sleep(float(interval))
    ctx.set_progress(100.0, "完成")
    return {"steps": steps, "interval": interval, "elapsed_hint": steps * interval}

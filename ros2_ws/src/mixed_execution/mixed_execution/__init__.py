"""mixed_execution: 混合功能执行服务包。

对系统暴露可执行的混合功能脚本 (视觉+底盘+机械臂组合动作),
通过 GenericCommand 服务 /mixed/list|execute|status|cancel 提供给
robot_control 后端的工作流引擎调用。
"""

from . import registry  # noqa: F401
from . import functions  # noqa: F401  (导入即注册所有混合功能)

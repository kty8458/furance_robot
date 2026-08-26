"""混合功能脚本目录。

新增混合功能: 在本目录新建模块并实现函数, 用 @mixed_function 装饰,
然后在下方 import 使其注册。节点启动时自动通过 /mixed/list 暴露。
"""

# 导入即注册
from . import demo  # noqa: F401

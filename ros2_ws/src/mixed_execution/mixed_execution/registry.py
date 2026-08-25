"""混合功能注册表。

混合功能 = 组合视觉/底盘/机械臂等多种能力的脚本, 以 Python 函数形式
写在 functions/ 目录下, 通过 @mixed_function 装饰器登记到注册表。
节点启动时自动枚举并通过 /mixed/list 服务暴露给系统 (工作流编辑器)。

params_schema 为简化字段描述列表, 每项:
    {name, type: "string"|"number"|"bool"|"select", description, default,
     options: [...] (仅 select), required: bool}
"""

import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger("mixed_execution.registry")

# 全局注册表: name -> MixedFunction
_REGISTRY: dict[str, "MixedFunction"] = {}
_LOCK = threading.Lock()


class MixedFunction:
    """一个已登记的混合功能。"""

    def __init__(self, name: str, description: str,
                 params_schema: list[dict], moves_base: bool,
                 fn: Callable):
        self.name = name
        self.description = description
        self.params_schema = params_schema or []
        self.moves_base = moves_base
        self.fn = fn

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "params_schema": self.params_schema,
            "moves_base": self.moves_base,
        }


def mixed_function(name: str, description: str = "",
                   params_schema: Optional[list[dict]] = None,
                   moves_base: bool = False) -> Callable:
    """登记混合功能的装饰器。

    Args:
        name: 功能唯一名 (工作流步骤引用)
        description: 功能描述 (前端展示)
        params_schema: 参数描述列表 (前端动态表单渲染)
        moves_base: 是否移动底盘 (工作流预检: 电量/地图)
    """

    def deco(fn: Callable) -> Callable:
        with _LOCK:
            if name in _REGISTRY:
                raise ValueError(f"Duplicate mixed function name: {name}")
            _REGISTRY[name] = MixedFunction(name, description,
                                            params_schema, moves_base, fn)
        logger.info("Registered mixed function: %s (moves_base=%s)", name, moves_base)
        return fn

    return deco


def list_functions() -> list[dict]:
    """返回所有已登记功能的元数据。"""
    with _LOCK:
        return [f.metadata() for f in _REGISTRY.values()]


def get_function(name: str) -> Optional[MixedFunction]:
    return _REGISTRY.get(name)


def default_params(name: str) -> dict[str, Any]:
    """返回某功能的默认参数 dict。"""
    f = _REGISTRY.get(name)
    if f is None:
        return {}
    return {p["name"]: p.get("default") for p in f.params_schema}

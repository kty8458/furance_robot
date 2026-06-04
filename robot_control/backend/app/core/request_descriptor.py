"""Translate (method, path, body) -> human-readable Chinese action description.

Used by the request-logging middleware to make backend logs human-friendly:
instead of "POST /api/v1/robot/robot_001/arm/teach/exec -> 200" we log
"执行示教点位 [left/preset_1] (moveJ) -> 200".
"""
from __future__ import annotations

import re
from typing import Any

# Path-pattern -> (action_template, body_fields)
# {placeholder} in path is captured; {field} in template substituted from body.
# Path patterns are simple regex (joined with ^ and $ implicit).

# Group 1 is the action template Chinese text. {body.X} pulls from request body.
# {p.X} pulls from path captures.
_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # (regex pattern matched against METHOD + " " + path, template)
    # ---- Robot basic commands ----
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/home$"),
     "回零位",
     "robot_id={p.rid}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/grab$"),
     "抓取动作",
     "robot_id={p.rid}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/place$"),
     "放置动作",
     "robot_id={p.rid}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/gripper$"),
     "夹爪控制",
     "arm={body.arm} action={body.action} force={body.force}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/lift$"),
     "升降控制",
     "direction={body.direction} distance={body.distance}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/charge$"),
     "充电控制",
     "action={body.action}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/enable$"),
     "使能控制",
     "enable={body.enable}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/clear-error$"),
     "清除告警",
     "robot_id={p.rid}"),

    # ---- Arm motion ----
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/arm/move$"),
     "机械臂运动",
     "arm={body.arm} method={body.method} coord={body.coordinate}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/arm/teach/save$"),
     "保存示教点",
     "arm={body.arm} name={body.name} method={body.method}"),
    (re.compile(r"^PUT /api/v1/robot/(?P<rid>[^/]+)/arm/teach/(?P<name>[^/]+)$"),
     "更新示教点",
     "arm={body.arm} name={p.name} method={body.method}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/arm/teach/exec$"),
     "执行示教点",
     "arm={body.arm} name={body.name} method={body.method}"),
    (re.compile(r"^DELETE /api/v1/robot/(?P<rid>[^/]+)/arm/teach/(?P<name>[^/]+)$"),
     "删除示教点",
     "name={p.name}"),

    # ---- Upper body ----
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/upper-body/waist$"),
     "腰部控制",
     "angle={body.waist_angle} speed={body.waist_speed}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/upper-body/ascend$"),
     "头部偏转",
     "pos={body.ascend_pos} speed={body.ascend_speed}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/upper-body/head$"),
     "头部俯仰",
     "angle={body.head_angle} speed={body.head_speed}"),

    # ---- Workflow ----
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/workflows/(?P<name>[^/]+)$"),
     "创建工作流",
     "name={p.name}"),
    (re.compile(r"^PUT /api/v1/robot/(?P<rid>[^/]+)/workflows/(?P<name>[^/]+)$"),
     "更新工作流",
     "name={p.name}"),
    (re.compile(r"^DELETE /api/v1/robot/(?P<rid>[^/]+)/workflows/(?P<name>[^/]+)$"),
     "删除工作流",
     "name={p.name}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/workflows/(?P<name>[^/]+)/execute$"),
     "执行工作流",
     "name={p.name} nav_params_count={body.nav_params|len}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/workflows/(?P<name>[^/]+)/cancel$"),
     "取消工作流",
     "name={p.name}"),

    # ---- Navigation ----
    (re.compile(r"^POST /api/v1/navigation/task/start$"),
     "启动导航任务",
     "map={body.map_name} tasks_count={body.tasks|len}"),
    (re.compile(r"^POST /api/v1/navigation/task/stop$"),
     "停止导航任务",
     ""),
    (re.compile(r"^POST /api/v1/navigation/recharge$"),
     "导航至充电点",
     "map={body.map_name} point={body.point_name}"),
    (re.compile(r"^POST /api/v1/navigation/token/refresh$"),
     "刷新底盘 token",
     ""),

    # ---- ROS2 node management ----
    (re.compile(r"^POST /api/v1/ros2/nodes/(?P<node>[^/]+)/start$"),
     "启动 ROS2 节点",
     "node={p.node}"),
    (re.compile(r"^POST /api/v1/ros2/nodes/(?P<node>[^/]+)/stop$"),
     "停止 ROS2 节点",
     "node={p.node}"),

    # ---- Camera ----
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/camera/publish/(?P<action>start|stop)$"),
     "相机发布",
     "action={p.action} camera={body.camera_id}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/camera/stream/(?P<action>start|stop)$"),
     "相机流",
     "action={p.action} camera={body.camera_id}"),
    (re.compile(r"^POST /api/v1/robot/(?P<rid>[^/]+)/camera/detect$"),
     "视觉检测",
     "camera={body.camera_id} scene={body.scene}"),
]


def _resolve_field(spec: str, path_match: re.Match, body: dict) -> str:
    """Resolve {p.X} / {body.X} / {body.X|len} into a string."""
    if spec.startswith("p."):
        key = spec[2:]
        return path_match.group(key) if key in path_match.groupdict() else "?"
    if spec.startswith("body."):
        rest = spec[5:]
        if "|" in rest:
            field, op = rest.split("|", 1)
            value = body.get(field) if isinstance(body, dict) else None
            if op == "len":
                try:
                    return str(len(value)) if value is not None else "0"
                except TypeError:
                    return "?"
            return str(value)
        return str(body.get(rest, "?")) if isinstance(body, dict) else "?"
    return spec


_PLACEHOLDER = re.compile(r"\{([^}]+)\}")


def describe_request(method: str, path: str, body: Any) -> str | None:
    """Return a human-friendly Chinese description, or None if no match.

    body is the parsed JSON body (or None for GET/empty).
    """
    key = f"{method} {path}"
    for pattern, action, params_template in _PATTERNS:
        m = pattern.match(key)
        if not m:
            continue
        if not params_template:
            return action

        def _sub(match: re.Match) -> str:
            return _resolve_field(match.group(1), m, body or {})

        rendered = _PLACEHOLDER.sub(_sub, params_template)
        return f"{action} [{rendered}]"
    return None

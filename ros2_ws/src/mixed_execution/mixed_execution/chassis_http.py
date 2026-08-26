"""底盘 HTTP 客户端 (供混合功能脚本调用)。

底盘调度走 HTTP 接口 (非 ROS2), 后端 robot_control 已有异步版本
(app/services/chassis_client.py)。本模块为混合执行节点内的同步版本,
供在执行线程中直接调用 (如: 视觉解算后驱动底盘定角度旋转)。

配置来源: config/mixed_config.yaml 的 chassis 段, 环境变量可覆盖:
    MIXED_CHASSIS_BASE_URL / MIXED_CHASSIS_TOKEN
"""

import logging
from typing import Any, Optional

import requests

logger = logging.getLogger("mixed_execution.chassis_http")


class ChassisHttpError(Exception):
    pass


class ChassisHttpClient:
    """同步底盘 HTTP 客户端。"""

    def __init__(self, base_url: str, token: str = "",
                 timeout: float = 30.0, verify_ssl: bool = False):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.verify = verify_ssl
        self._session.headers.update({"Content-Type": "application/json"})
        if token:
            self._session.headers.update({"Authorization": f"Bearer {token}"})

    @classmethod
    def from_config(cls, cfg: Optional[dict]) -> "ChassisHttpClient":
        import os
        cfg = cfg or {}
        base_url = os.environ.get("MIXED_CHASSIS_BASE_URL", cfg.get("base_url", ""))
        token = os.environ.get("MIXED_CHASSIS_TOKEN", cfg.get("token", ""))
        timeout = float(cfg.get("timeout", 30.0))
        if not base_url:
            logger.warning("Chassis base_url not configured, chassis calls will fail")
        return cls(base_url, token, timeout)

    def _post(self, path: str, body: Optional[dict] = None) -> dict:
        if not self._base_url:
            raise ChassisHttpError("Chassis base_url not configured")
        url = f"{self._base_url}{path}"
        try:
            resp = self._session.post(url, json=body or {}, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise ChassisHttpError(f"Chassis request failed: {url} -> {e}") from e

    def _get(self, path: str) -> dict:
        if not self._base_url:
            raise ChassisHttpError("Chassis base_url not configured")
        url = f"{self._base_url}{path}"
        try:
            resp = self._session.get(url, timeout=self._timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise ChassisHttpError(f"Chassis request failed: {url} -> {e}") from e

    # ---- 移动原语 ----

    def move_with_params(self, mode: int, linear_velocity: float = 0.0,
                         slip_angle: float = 0.0, angular_velocity: float = 0.0,
                         target_distance: float = 0.0,
                         target_angle: float = 0.0) -> dict:
        """定距离/定角度移动 (阻塞至底盘执行完)。

        mode: 1=定距离, 2=定角度 (底盘原地旋转)
        """
        return self._post("/cmd/move_with_params", {
            "mode": mode,
            "linear_velocity": linear_velocity,
            "slip_angle": slip_angle,
            "angular_velocity": angular_velocity,
            "target_distance": target_distance,
            "target_angle": target_angle,
        })

    def cancel_move_with_params(self) -> dict:
        """取消正在执行的定距离/定角度移动。"""
        return self._post("/cmd/cancel_move_with_params")

    def rotate(self, angle_deg: float, angular_velocity: float = 30.0) -> dict:
        """底盘定角度旋转 (mode=2)。angle_deg 正负决定方向。"""
        return self.move_with_params(mode=2, angular_velocity=angular_velocity,
                                     target_angle=angle_deg)

    def move_distance(self, distance_m: float, linear_velocity: float = 0.2,
                      slip_angle: float = 0.0) -> dict:
        """底盘定距离直线移动 (mode=1)。"""
        return self.move_with_params(mode=1, linear_velocity=linear_velocity,
                                     slip_angle=slip_angle,
                                     target_distance=distance_m)

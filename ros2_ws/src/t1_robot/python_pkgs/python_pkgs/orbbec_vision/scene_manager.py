"""场景管理器 — 场景 yaml 文件 CRUD 操作。"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml

logger = logging.getLogger("orbbec_vision.scene_manager")


def _to_json_safe(obj):
    """递归将 numpy 类型转为纯 Python 类型，确保 yaml/json 可序列化。"""
    import numpy as np
    if isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_to_json_safe(v) for v in obj]
    return obj

DEFAULT_SCENE_TEMPLATE = {
    "scene_id": "",
    "description": "",
    "qr_transforms": [],
    "vision_models": [],
}


def normalize_point(p: Dict[str, Any]) -> Dict[str, Any]:
    """将点位数据规范为新格式 (qr_ids + T_qr_ee_per_id)。

    旧字段 qr_id + T_qr_workspace 会被转换为新字段。
    """
    out = dict(p)
    if "qr_ids" not in out:
        qid = out.get("qr_id")
        out["qr_ids"] = [qid] if qid is not None else []
    if "T_qr_ee_per_id" not in out:
        T_old = out.get("T_qr_workspace")
        qid = out.get("qr_id")
        out["T_qr_ee_per_id"] = {str(qid): T_old} if (T_old and qid is not None) else {}
    return out


class SceneManager:
    """管理场景 yaml 文件，每个场景一个 <scene_id>.yaml 文件。"""

    def __init__(self, scenes_dir: str):
        self._dir = Path(scenes_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        logger.info("SceneManager initialized, scenes_dir=%s", self._dir)

    # ---- 内部 ----

    def _path(self, scene_id: str) -> Path:
        return self._dir / f"{scene_id}.yaml"

    def _load(self, scene_id: str) -> Optional[dict]:
        p = self._path(scene_id)
        if not p.exists():
            return None
        with open(p) as f:
            return yaml.safe_load(f) or {}

    def _save(self, scene_id: str, data: dict):
        data["scene_id"] = scene_id
        data = _to_json_safe(data)
        with open(self._path(scene_id), "w") as f:
            yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)
        logger.info("Scene saved: %s", scene_id)

    # ---- 公共 API ----

    def list_scenes(self) -> List[Dict[str, Any]]:
        """返回所有场景摘要列表。"""
        result = []
        for p in sorted(self._dir.glob("*.yaml")):
            sid = p.stem
            try:
                data = self._load(sid)
                if data:
                    result.append({
                        "scene_id": sid,
                        "description": data.get("description", ""),
                        "qr_count": len(data.get("qr_transforms", [])),
                        "model_count": len(data.get("vision_models", [])),
                    })
            except Exception:
                logger.exception("Failed to read scene: %s", sid)
        logger.info("list_scenes: %d scenes found", len(result))
        return result

    def get_scene(self, scene_id: str) -> Optional[dict]:
        """返回场景完整数据。"""
        data = self._load(scene_id)
        if data is None:
            logger.warning("get_scene: %s not found", scene_id)
        else:
            logger.info("get_scene: %s loaded, qr=%d, models=%d",
                        scene_id, len(data.get("qr_transforms", [])),
                        len(data.get("vision_models", [])))
        return data

    def create_scene(self, scene_id: str, description: str = "") -> bool:
        """新建场景。"""
        if self._path(scene_id).exists():
            logger.warning("create_scene: %s already exists", scene_id)
            return False
        data = dict(DEFAULT_SCENE_TEMPLATE)
        data["scene_id"] = scene_id
        data["description"] = description
        self._save(scene_id, data)
        logger.info("create_scene: %s created", scene_id)
        return True

    def delete_scene(self, scene_id: str) -> bool:
        """删除场景文件。"""
        p = self._path(scene_id)
        if not p.exists():
            logger.warning("delete_scene: %s not found", scene_id)
            return False
        p.unlink()
        logger.info("delete_scene: %s deleted", scene_id)
        return True

    def add_point(self, scene_id: str, name: str, arm: str,
                  marker_size: float,
                  qr_ids: Optional[List[int]] = None,
                  T_qr_ee_per_id: Optional[Dict[str, Any]] = None,
                  T_qr_workspace: Optional[Dict[str, Any]] = None,
                  qr_id: Optional[int] = None,
                  stream_type: str = "color") -> bool:
        """添加标定点到场景。

        新格式: qr_ids (允许列表, 空=通配) + T_qr_ee_per_id (每个 QR 的 T_qr_ee).
        旧格式: qr_id (单个) + T_qr_workspace 仍兼容, 内部转新格式存储.
        """
        data = self._load(scene_id)
        if data is None:
            logger.warning("add_point: scene %s not found", scene_id)
            return False

        # 兼容旧格式: 单 qr_id + T_qr_workspace → 转新格式
        if qr_ids is None:
            qr_ids = [qr_id] if qr_id is not None else []
        if T_qr_ee_per_id is None and T_qr_workspace is not None and qr_id is not None:
            T_qr_ee_per_id = {str(qr_id): T_qr_workspace}
        if T_qr_ee_per_id is None:
            T_qr_ee_per_id = {}

        # 删除同名点
        data.setdefault("qr_transforms", [])
        data["qr_transforms"] = [p for p in data["qr_transforms"] if p.get("name") != name]
        data["qr_transforms"].append({
            "name": name,
            "arm": arm,
            "marker_size": marker_size,
            "stream_type": stream_type,
            "qr_ids": qr_ids,
            "T_qr_ee_per_id": T_qr_ee_per_id,
        })
        self._save(scene_id, data)
        logger.info("add_point: scene=%s point=%s qr_ids=%s arm=%s per_id_count=%d",
                    scene_id, name, qr_ids, arm, len(T_qr_ee_per_id))
        return True

    def delete_point(self, scene_id: str, point_name: str) -> bool:
        """从场景删除标定点。"""
        data = self._load(scene_id)
        if data is None:
            return False
        before = len(data.get("qr_transforms", []))
        data["qr_transforms"] = [p for p in data.get("qr_transforms", [])
                                 if p.get("name") != point_name]
        if len(data["qr_transforms"]) == before:
            logger.warning("delete_point: point %s not found in %s", point_name, scene_id)
            return False
        self._save(scene_id, data)
        logger.info("delete_point: scene=%s point=%s deleted", scene_id, point_name)
        return True

    def update_point(self, scene_id: str, point_name: str, **kwargs) -> bool:
        """更新标定点字段。"""
        data = self._load(scene_id)
        if data is None:
            return False
        for p in data.get("qr_transforms", []):
            if p.get("name") == point_name:
                for k, v in kwargs.items():
                    p[k] = v
                self._save(scene_id, data)
                logger.info("update_point: scene=%s point=%s updated %s",
                            scene_id, point_name, list(kwargs.keys()))
                return True
        logger.warning("update_point: point %s not found in %s", point_name, scene_id)
        return False

    def find_point(self, scene_id: str, point_name: str) -> Optional[dict]:
        """查找标定点 (自动规范为新格式)。"""
        data = self._load(scene_id)
        if data is None:
            return None
        for p in data.get("qr_transforms", []):
            if p.get("name") == point_name:
                return normalize_point(p)
        return None
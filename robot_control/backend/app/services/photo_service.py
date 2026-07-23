"""照片集管理服务 - 训练数据采集 (YOLO) 的照片/相册 CRUD。

存储布局 (photo_data_dir):
    <photo_data_dir>/<scene_id>/index.json                  相册索引
    <photo_data_dir>/<scene_id>/<album_id>/<photo_id>.jpg  彩色帧
    <photo_data_dir>/<scene_id>/<album_id>/<photo_id>.json 照片元信息

照片仅以 scene_id 关联场景 (场景/点位标定数据仍在 ROS2 scene_manager)。
"""

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

# 安全名称: 允许 Unicode 字母/数字/下划线/中划线/点 (兼容中文 scene_id),
# 路径穿越靠 _safe_name 内的显式检查防护, 不依赖此正则。
_SAFE_NAME_RE = re.compile(r"^[\w.\-]+$", re.UNICODE)


class PhotoError(Exception):
    """照片服务业务异常, code 供 API 层返回, message 供前端展示。"""

    def __init__(self, message: str, code: int = 3401):
        super().__init__(message)
        self.code = code
        self.message = message


def _safe_name(value: str, field: str) -> str:
    """校验 scene_id/album_id/photo_id 为安全文件名片段 (防路径穿越)。

    允许中文等 Unicode 标识符, 禁止: 空值、路径分隔符 / \\、穿越 .. 、开头点、空字符、
    含空格/冒号等非常规字符。
    """
    if not value or not isinstance(value, str):
        raise PhotoError(f"非法 {field}: {value!r}")
    if "\x00" in value or "/" in value or "\\" in value or value in (".", "..") or value[0] == ".":
        raise PhotoError(f"非法 {field}: {value!r}")
    if not _SAFE_NAME_RE.match(value):
        raise PhotoError(f"非法 {field}: {value!r}")
    return value


def _sanitize_album_name(name: str) -> str:
    """相册显示名清洗: 去首尾空白, 截断长度。允许中文等, 仅用于展示不用于路径。"""
    name = (name or "").strip()
    if not name:
        raise PhotoError("相册名称不能为空")
    return name[:64]


class PhotoService:
    """管理场景下的照片集与照片文件。"""

    def __init__(self, photos_dir: str):
        self._dir = Path(photos_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        logger.info("PhotoService initialized, photos_dir=%s", self._dir)

    # ---- 路径 ----

    def _scene_dir(self, scene_id: str) -> Path:
        return self._dir / _safe_name(scene_id, "scene_id")

    def _album_dir(self, scene_id: str, album_id: str) -> Path:
        return self._scene_dir(scene_id) / _safe_name(album_id, "album_id")

    def _index_path(self, scene_id: str) -> Path:
        return self._scene_dir(scene_id) / "index.json"

    def _photo_stem(self, photo_id: str) -> str:
        return _safe_name(photo_id, "photo_id")

    # ---- 索引读写 ----

    def _load_index(self, scene_id: str) -> dict:
        p = self._index_path(scene_id)
        if not p.exists():
            return {"albums": []}
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f) or {"albums": []}
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to read album index: %s", p)
            return {"albums": []}

    def _save_index(self, scene_id: str, data: dict) -> None:
        scene_dir = self._scene_dir(scene_id)
        scene_dir.mkdir(parents=True, exist_ok=True)
        with open(self._index_path(scene_id), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- 相册 ----

    def list_albums(self, scene_id: str) -> list[dict[str, Any]]:
        _safe_name(scene_id, "scene_id")
        with self._lock:
            data = self._load_index(scene_id)
        albums = []
        for a in data.get("albums", []):
            album_dir = self._album_dir(scene_id, a["id"])
            photo_count = sum(1 for _ in album_dir.glob("*.jpg")) if album_dir.exists() else 0
            albums.append({
                "id": a["id"],
                "name": a.get("name", a["id"]),
                "created_at": a.get("created_at", ""),
                "photo_count": photo_count,
            })
        return albums

    def _find_album(self, data: dict, album_id: str) -> Optional[dict]:
        for a in data.get("albums", []):
            if a["id"] == album_id:
                return a
        return None

    def create_album(self, scene_id: str, name: str) -> dict[str, Any]:
        _safe_name(scene_id, "scene_id")
        name = _sanitize_album_name(name)
        with self._lock:
            data = self._load_index(scene_id)
            # 名称去重: 重名追加 (2) (3) ...
            existing = {a.get("name") for a in data.get("albums", [])}
            final_name = name
            suffix = 2
            while final_name in existing:
                final_name = f"{name} ({suffix})"
                suffix += 1
            album_id = f"al_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            album = {
                "id": album_id,
                "name": final_name,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            data.setdefault("albums", []).append(album)
            self._album_dir(scene_id, album_id).mkdir(parents=True, exist_ok=True)
            self._save_index(scene_id, data)
            logger.info("Album created: scene=%s album=%s(%s)", scene_id, album_id, final_name)
            return {**album, "photo_count": 0}

    def delete_album(self, scene_id: str, album_id: str) -> bool:
        _safe_name(scene_id, "scene_id")
        _safe_name(album_id, "album_id")
        with self._lock:
            data = self._load_index(scene_id)
            album = self._find_album(data, album_id)
            if album is None:
                raise PhotoError(f"照片集不存在: {album_id}")
            data["albums"] = [a for a in data.get("albums", []) if a["id"] != album_id]
            self._save_index(scene_id, data)
            album_dir = self._album_dir(scene_id, album_id)
            if album_dir.exists():
                import shutil
                shutil.rmtree(album_dir, ignore_errors=True)
            logger.info("Album deleted: scene=%s album=%s", scene_id, album_id)
            return True

    def get_album(self, scene_id: str, album_id: str) -> dict[str, Any]:
        """返回相册元信息 (不存在则抛 PhotoError)。"""
        _safe_name(scene_id, "scene_id")
        _safe_name(album_id, "album_id")
        with self._lock:
            data = self._load_index(scene_id)
            album = self._find_album(data, album_id)
        if album is None:
            raise PhotoError(f"照片集不存在: {album_id}")
        return album

    # ---- 照片 ----

    def list_photos(self, scene_id: str, album_id: str) -> list[dict[str, Any]]:
        self.get_album(scene_id, album_id)  # 校验存在
        album_dir = self._album_dir(scene_id, album_id)
        photos = []
        for jpg in sorted(album_dir.glob("*.jpg"), key=lambda p: p.name):
            stem = jpg.stem
            meta = self._load_photo_meta(scene_id, album_id, stem)
            photos.append({
                "id": stem,
                "name": jpg.name,
                "size": jpg.stat().st_size,
                "created_at": meta.get("captured_at", datetime.fromtimestamp(jpg.stat().st_mtime).isoformat(timespec="seconds")),
                "camera_id": meta.get("camera_id", ""),
                "stream_type": meta.get("stream_type", ""),
                "note": meta.get("note", ""),
            })
        return photos

    def _load_photo_meta(self, scene_id: str, album_id: str, photo_id: str) -> dict:
        p = self._album_dir(scene_id, album_id) / f"{self._photo_stem(photo_id)}.json"
        if not p.exists():
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f) or {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save_photo(self, scene_id: str, album_id: str, jpeg_bytes: bytes,
                   camera_id: str = "", stream_type: str = "", note: str = "") -> dict[str, Any]:
        """保存一帧 JPEG 到指定相册, 返回照片记录。"""
        self.get_album(scene_id, album_id)  # 校验相册存在
        if not jpeg_bytes:
            raise PhotoError("空图片数据")
        photo_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        album_dir = self._album_dir(scene_id, album_id)
        jpg_path = album_dir / f"{photo_id}.jpg"
        meta_path = album_dir / f"{photo_id}.json"
        # 防极小概率同毫秒冲突
        i = 1
        while jpg_path.exists():
            photo_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{i}"
            jpg_path = album_dir / f"{photo_id}.jpg"
            meta_path = album_dir / f"{photo_id}.json"
            i += 1
        jpg_path.write_bytes(jpeg_bytes)
        meta = {
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "camera_id": camera_id,
            "stream_type": stream_type,
            "note": (note or "")[:200],
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        logger.info("Photo saved: scene=%s album=%s photo=%s size=%d",
                    scene_id, album_id, photo_id, len(jpeg_bytes))
        return {
            "id": photo_id,
            "name": jpg_path.name,
            "size": len(jpeg_bytes),
            "created_at": meta["captured_at"],
            "camera_id": meta["camera_id"],
            "stream_type": meta["stream_type"],
            "note": meta["note"],
        }

    def get_photo_path(self, scene_id: str, album_id: str, photo_id: str) -> Path:
        """返回照片文件 Path (不存在则抛 PhotoError)。"""
        self.get_album(scene_id, album_id)
        jpg = self._album_dir(scene_id, album_id) / f"{self._photo_stem(photo_id)}.jpg"
        if not jpg.is_file():
            raise PhotoError(f"照片不存在: {photo_id}")
        return jpg

    def delete_photo(self, scene_id: str, album_id: str, photo_id: str) -> bool:
        self.get_album(scene_id, album_id)
        stem = self._photo_stem(photo_id)
        album_dir = self._album_dir(scene_id, album_id)
        jpg = album_dir / f"{stem}.jpg"
        meta = album_dir / f"{stem}.json"
        if not jpg.is_file():
            raise PhotoError(f"照片不存在: {photo_id}")
        jpg.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)
        logger.info("Photo deleted: scene=%s album=%s photo=%s", scene_id, album_id, photo_id)
        return True

    # ---- 打包下载 ----

    def stream_album_zip(self, scene_id: str, album_id: str) -> Iterator[bytes]:
        """生成相册 zip 字节流 (惰性, 流式写入临时文件后分块读出)。

        调用方负责消费完毕 (generator 会在 finally 删除临时文件)。
        """
        self.get_album(scene_id, album_id)
        album_dir = self._album_dir(scene_id, album_id)
        photos = sorted(album_dir.glob("*.jpg"), key=lambda p: p.name)
        if not photos:
            raise PhotoError("照片集为空, 无法打包下载")

        import tempfile
        import zipfile

        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for jpg in photos:
                    # 压缩包内文件名用相册名 + 原文件名
                    zf.write(jpg, arcname=jpg.name)
            with open(tmp_path, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    yield chunk
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    # ---- 级联 ----

    def delete_scene_photos(self, scene_id: str) -> bool:
        """删除场景下所有照片集 (场景被删除时级联调用)。"""
        _safe_name(scene_id, "scene_id")
        scene_dir = self._scene_dir(scene_id)
        if not scene_dir.exists():
            return False
        import shutil
        shutil.rmtree(scene_dir, ignore_errors=True)
        logger.info("Scene photos deleted: scene=%s", scene_id)
        return True

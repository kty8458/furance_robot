"""照片采集 HTTP 接口 - 为 YOLO 训练数据采集提供拍照/相册/下载能力。

Routes (prefix /api/v1/robot/{robot_id}/camera/photos):
  POST /capture                                拍照存入指定相册 (前端取当前彩色帧 base64 上传)
  GET  /{scene_id}/albums                      列出场景下所有相册
  POST /{scene_id}/albums                      新建相册 {name}
  DELETE /{scene_id}/albums/{album_id}          删除相册 (含其下照片)
  GET  /{scene_id}/albums/{album_id}/photos     列出相册内照片
  DELETE /{scene_id}/albums/{album_id}/photos/{photo_id}  删除单张
  GET  /{scene_id}/albums/{album_id}/photos/{photo_id}/file  单张查看/下载
  GET  /{scene_id}/albums/{album_id}/download   打包下载相册 zip
"""

import base64
import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from furance_shared.protocol.http_schema import ApiResponse
from app.services.photo_service import PhotoError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/robot/{robot_id}/camera/photos", tags=["camera-photos"])

# 错误码: 3xxx 业务类, 34xx 拍照相关
ERR_INVALID = 3404   # 参数非法 / 数据无效
ERR_NOT_FOUND = 3402  # 资源不存在
ERR_SAVE = 3403       # 拍照/保存失败


def _photo_service(request: Request):
    svc = getattr(request.app.state, "photo_service", None)
    if svc is None:
        raise HTTPException(status_code=500, detail={"code": 3001, "message": "PhotoService 未初始化"})
    return svc


def _to_response_error(e: PhotoError):
    return ApiResponse(code=e.code, message=e.message)


@router.post("/capture", response_model=ApiResponse)
async def capture(robot_id: str, req: dict, request: Request):
    """拍照: 取前端上传的彩色帧 base64 存入相册。

    Body: {camera_id, scene_id, album_id, stream_type?, note?, jpeg_b64}
    """
    svc = _photo_service(request)
    scene_id = (req.get("scene_id") or "").strip()
    album_id = (req.get("album_id") or "").strip()
    jpeg_b64 = req.get("jpeg_b64") or ""
    if not scene_id or not album_id or not jpeg_b64:
        return ApiResponse(code=ERR_INVALID, message="缺少 scene_id/album_id/jpeg_b64")
    try:
        jpeg_bytes = base64.b64decode(jpeg_b64)
    except Exception:
        return ApiResponse(code=ERR_INVALID, message="jpeg_b64 不是合法 base64")
    try:
        photo = svc.save_photo(
            scene_id=scene_id,
            album_id=album_id,
            jpeg_bytes=jpeg_bytes,
            camera_id=(req.get("camera_id") or "").strip(),
            stream_type=(req.get("stream_type") or "").strip(),
            note=(req.get("note") or "").strip(),
        )
        return ApiResponse(data=photo)
    except PhotoError as e:
        return _to_response_error(e)
    except Exception as e:
        logger.exception("Capture failed: scene=%s album=%s", scene_id, album_id)
        return ApiResponse(code=ERR_SAVE, message=f"拍照失败: {e}")


@router.get("/{scene_id}/albums", response_model=ApiResponse)
async def list_albums(robot_id: str, scene_id: str, request: Request):
    svc = _photo_service(request)
    try:
        return ApiResponse(data=svc.list_albums(scene_id))
    except PhotoError as e:
        return _to_response_error(e)


@router.post("/{scene_id}/albums", response_model=ApiResponse)
async def create_album(robot_id: str, scene_id: str, req: dict, request: Request):
    svc = _photo_service(request)
    name = (req.get("name") or "").strip()
    try:
        album = svc.create_album(scene_id, name)
        return ApiResponse(data=album)
    except PhotoError as e:
        return _to_response_error(e)


@router.delete("/{scene_id}/albums/{album_id}", response_model=ApiResponse)
async def delete_album(robot_id: str, scene_id: str, album_id: str, request: Request):
    svc = _photo_service(request)
    try:
        svc.delete_album(scene_id, album_id)
        return ApiResponse(message="照片集已删除")
    except PhotoError as e:
        return _to_response_error(e)


@router.get("/{scene_id}/albums/{album_id}/photos", response_model=ApiResponse)
async def list_photos(robot_id: str, scene_id: str, album_id: str, request: Request):
    svc = _photo_service(request)
    try:
        return ApiResponse(data=svc.list_photos(scene_id, album_id))
    except PhotoError as e:
        return _to_response_error(e)


@router.delete("/{scene_id}/albums/{album_id}/photos/{photo_id}", response_model=ApiResponse)
async def delete_photo(robot_id: str, scene_id: str, album_id: str, photo_id: str, request: Request):
    svc = _photo_service(request)
    try:
        svc.delete_photo(scene_id, album_id, photo_id)
        return ApiResponse(message="照片已删除")
    except PhotoError as e:
        return _to_response_error(e)


@router.get("/{scene_id}/albums/{album_id}/photos/{photo_id}/file")
async def get_photo_file(robot_id: str, scene_id: str, album_id: str, photo_id: str, request: Request):
    svc = _photo_service(request)
    try:
        path = svc.get_photo_path(scene_id, album_id, photo_id)
    except PhotoError as e:
        raise HTTPException(status_code=404, detail={"code": ERR_NOT_FOUND, "message": e.message})
    return FileResponse(path=str(path), media_type="image/jpeg", filename=path.name)


@router.get("/{scene_id}/albums/{album_id}/download")
async def download_album_zip(robot_id: str, scene_id: str, album_id: str, request: Request):
    svc = _photo_service(request)
    try:
        # 先校验相册存在并取名称用于下载文件名
        album = svc.get_album(scene_id, album_id)
    except PhotoError as e:
        raise HTTPException(status_code=404, detail={"code": ERR_NOT_FOUND, "message": e.message})
    try:
        stream = svc.stream_album_zip(scene_id, album_id)
    except PhotoError as e:
        raise HTTPException(status_code=400, detail={"code": ERR_INVALID, "message": e.message})
    # Content-Disposition: filename= 仅允许 ASCII (latin-1), filename* 用 RFC 5987
    # 编码 UTF-8 文本。scene_id/相册名可能含中文, 必须整体进 filename*。
    ascii_name = album_id  # album_id 形如 al_xxx, 保证纯 ASCII
    utf8_name = quote(f"{scene_id}_{album.get('name', album_id)}")
    disposition = f"attachment; filename=\"{ascii_name}.zip\"; filename*=UTF-8''{utf8_name}.zip"
    return StreamingResponse(
        stream,
        media_type="application/zip",
        headers={"Content-Disposition": disposition},
    )

"""Photo API 集成测试 - 拍照/相册/照片/单张文件/zip 下载。"""

import base64
import io
import zipfile

import pytest

ROBOT_ID = "robot_001"


def _b64(payload: bytes) -> str:
    return base64.b64encode(payload).decode("ascii")


def _jpeg():
    return b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"\xff\xd9"


@pytest.mark.asyncio
async def test_capture_and_list(client):
    # 新建相册
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums",
                          json={"name": "抓取训练"})
    assert r.status_code == 200
    assert r.json()["code"] == 0
    album = r.json()["data"]
    album_id = album["id"]

    # 拍照
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "camera_id": "head", "scene_id": "scene_a", "album_id": album_id,
        "stream_type": "color", "note": "n1", "jpeg_b64": _b64(_jpeg()),
    })
    assert r.status_code == 200
    assert r.json()["code"] == 0
    photo = r.json()["data"]
    assert photo["camera_id"] == "head"

    # 列出照片
    r = await client.get(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums/{album_id}/photos")
    assert r.json()["code"] == 0
    photos = r.json()["data"]
    assert len(photos) == 1
    assert photos[0]["id"] == photo["id"]

    # 相册列表 photo_count
    r = await client.get(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums")
    assert r.json()["data"][0]["photo_count"] == 1


@pytest.mark.asyncio
async def test_capture_missing_fields(client):
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture",
                          json={"scene_id": "scene_a", "album_id": "", "jpeg_b64": ""})
    assert r.json()["code"] != 0


@pytest.mark.asyncio
async def test_capture_nonexistent_album(client):
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "scene_id": "scene_a", "album_id": "al_nope", "jpeg_b64": _b64(_jpeg()),
    })
    assert r.json()["code"] != 0
    assert "不存在" in r.json()["message"]


@pytest.mark.asyncio
async def test_photo_file_download(client):
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums",
                          json={"name": "集"})
    album_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "scene_id": "scene_a", "album_id": album_id, "jpeg_b64": _b64(_jpeg()),
    })
    photo_id = r.json()["data"]["id"]

    r = await client.get(
        f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums/{album_id}/photos/{photo_id}/file"
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == _jpeg()


@pytest.mark.asyncio
async def test_album_zip_download(client):
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums",
                          json={"name": "集"})
    album_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "scene_id": "scene_a", "album_id": album_id, "jpeg_b64": _b64(_jpeg()),
    })
    await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "scene_id": "scene_a", "album_id": album_id, "jpeg_b64": _b64(b"\xff\xd8\xff\xe1" + b"\x00" * 8 + b"\xff\xd9"),
    })

    r = await client.get(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums/{album_id}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert len(zf.namelist()) == 2


@pytest.mark.asyncio
async def test_album_zip_download_chinese_names(client):
    """中文 scene_id + 中文相册名打包下载, Content-Disposition 不得触发 latin-1 编码错误。"""
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/采集场景/albums",
                          json={"name": "抓取集"})
    assert r.json()["code"] == 0
    album_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "scene_id": "采集场景", "album_id": album_id, "jpeg_b64": _b64(_jpeg()),
    })
    r = await client.get(f"/api/v1/robot/{ROBOT_ID}/camera/photos/采集场景/albums/{album_id}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    # filename* 应含百分号编码的 UTF-8 中文, filename= 仍是纯 ASCII
    assert "filename*=UTF-8''" in r.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert len(zf.namelist()) == 1


@pytest.mark.asyncio
async def test_delete_photo_and_album(client):
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums",
                          json={"name": "集"})
    album_id = r.json()["data"]["id"]
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "scene_id": "scene_a", "album_id": album_id, "jpeg_b64": _b64(_jpeg()),
    })
    photo_id = r.json()["data"]["id"]

    r = await client.delete(
        f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums/{album_id}/photos/{photo_id}"
    )
    assert r.json()["code"] == 0

    r = await client.delete(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums/{album_id}")
    assert r.json()["code"] == 0
    # 再删一次应失败
    r = await client.delete(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums/{album_id}")
    assert r.json()["code"] != 0


@pytest.mark.asyncio
async def test_path_traversal_blocked(client):
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums",
                          json={"name": "集"})
    album_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "scene_id": "scene_a", "album_id": album_id, "jpeg_b64": _b64(_jpeg()),
    })
    # 尝试路径穿越访问其它文件
    r = await client.get(
        f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_a/albums/{album_id}/photos/..%2f..%2findex/file"
    )
    assert r.status_code in (400, 404)


@pytest.mark.asyncio
async def test_scene_delete_cascades_photos(client):
    """删除场景应级联清理照片 (camera scene delete -> photo_service)。"""
    # MockCameraClient.scene_operation 对 delete 返回 success
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_cascade/albums",
                          json={"name": "集"})
    album_id = r.json()["data"]["id"]
    await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/photos/capture", json={
        "scene_id": "scene_cascade", "album_id": album_id, "jpeg_b64": _b64(_jpeg()),
    })
    # 删除场景 (走 camera scene API, MockCameraClient 返回 success)
    r = await client.post(f"/api/v1/robot/{ROBOT_ID}/camera/scene", json={
        "action": "delete", "scene_id": "scene_cascade", "params": {},
    })
    assert r.json()["code"] == 0
    # 照片应已清空
    r = await client.get(f"/api/v1/robot/{ROBOT_ID}/camera/photos/scene_cascade/albums")
    assert r.json()["data"] == []

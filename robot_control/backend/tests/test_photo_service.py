"""PhotoService 单元测试 - 相册/照片 CRUD, zip, 越界防护, 级联清理。"""

import io
import zipfile

import pytest

from app.services.photo_service import PhotoError, PhotoService

ROBOT_ID = "robot_001"


@pytest.fixture
def photo_service(tmp_path):
    return PhotoService(str(tmp_path / "photos"))


def _jpeg_bytes(color=b"\xff\xd8\xff\xe0"):
    """最小合法 JPEG 头 + 填充。"""
    return color + b"\x00" * 16 + b"\xff\xd9"


class TestAlbumCrud:
    def test_create_and_list_album(self, photo_service):
        album = photo_service.create_album("scene_a", "抓取训练")
        assert album["name"] == "抓取训练"
        assert album["photo_count"] == 0
        albums = photo_service.list_albums("scene_a")
        assert len(albums) == 1
        assert albums[0]["id"] == album["id"]
        assert albums[0]["name"] == "抓取训练"

    def test_create_album_duplicate_name_suffix(self, photo_service):
        photo_service.create_album("scene_a", "集")
        b = photo_service.create_album("scene_a", "集")
        c = photo_service.create_album("scene_a", "集")
        assert b["name"] == "集 (2)"
        assert c["name"] == "集 (3)"

    def test_create_album_empty_name_raises(self, photo_service):
        with pytest.raises(PhotoError):
            photo_service.create_album("scene_a", "")

    def test_delete_album_removes_photos(self, photo_service):
        album = photo_service.create_album("scene_a", "集")
        photo_service.save_photo("scene_a", album["id"], _jpeg_bytes())
        assert len(photo_service.list_photos("scene_a", album["id"])) == 1
        photo_service.delete_album("scene_a", album["id"])
        with pytest.raises(PhotoError):
            photo_service.list_photos("scene_a", album["id"])
        assert photo_service.list_albums("scene_a") == []


class TestPhotoCrud:
    def test_save_and_list_photo(self, photo_service):
        album = photo_service.create_album("scene_a", "集")
        data = _jpeg_bytes()
        photo = photo_service.save_photo("scene_a", album["id"], data,
                                        camera_id="head", stream_type="color", note="n1")
        assert photo["size"] == len(data)
        assert photo["camera_id"] == "head"
        assert photo["stream_type"] == "color"
        assert photo["note"] == "n1"
        photos = photo_service.list_photos("scene_a", album["id"])
        assert len(photos) == 1
        assert photos[0]["id"] == photo["id"]

    def test_get_photo_path(self, photo_service):
        album = photo_service.create_album("scene_a", "集")
        photo = photo_service.save_photo("scene_a", album["id"], _jpeg_bytes())
        p = photo_service.get_photo_path("scene_a", album["id"], photo["id"])
        assert p.is_file()
        assert p.read_bytes() == _jpeg_bytes()

    def test_delete_photo(self, photo_service):
        album = photo_service.create_album("scene_a", "集")
        photo = photo_service.save_photo("scene_a", album["id"], _jpeg_bytes())
        photo_service.delete_photo("scene_a", album["id"], photo["id"])
        with pytest.raises(PhotoError):
            photo_service.get_photo_path("scene_a", album["id"], photo["id"])

    def test_save_to_nonexistent_album_raises(self, photo_service):
        with pytest.raises(PhotoError):
            photo_service.save_photo("scene_a", "al_noexist", _jpeg_bytes())


class TestZipDownload:
    def test_stream_album_zip(self, photo_service):
        album = photo_service.create_album("scene_a", "集")
        photo_service.save_photo("scene_a", album["id"], _jpeg_bytes())
        photo_service.save_photo("scene_a", album["id"], _jpeg_bytes(b"\xff\xd8\xff\xe1"))
        buf = io.BytesIO()
        for chunk in photo_service.stream_album_zip("scene_a", album["id"]):
            buf.write(chunk)
        buf.seek(0)
        zf = zipfile.ZipFile(buf)
        names = zf.namelist()
        assert len(names) == 2
        assert all(n.endswith(".jpg") for n in names)

    def test_zip_empty_album_raises(self, photo_service):
        album = photo_service.create_album("scene_a", "集")
        with pytest.raises(PhotoError):
            list(photo_service.stream_album_zip("scene_a", album["id"]))


class TestPathSafety:
    @pytest.mark.parametrize("bad", ["", "..", "a/b", "a\\b", "a/../b", ".hidden", "a b", "a:b"])
    def test_unsafe_scene_id_rejected(self, photo_service, bad):
        with pytest.raises(PhotoError):
            photo_service.create_album(bad, "x")

    @pytest.mark.parametrize("bad", ["", "..", "a/b", "a/../b", "a b"])
    def test_unsafe_album_id_rejected(self, photo_service, bad):
        with pytest.raises(PhotoError):
            photo_service.delete_album("scene_a", bad)

    @pytest.mark.parametrize("bad", ["", "..", "a/b", "a/../b", "a b"])
    def test_unsafe_photo_id_rejected(self, photo_service, bad):
        album = photo_service.create_album("scene_a", "集")
        with pytest.raises(PhotoError):
            photo_service.get_photo_path("scene_a", album["id"], bad)


class TestUnicodeNames:
    """中文 scene_id 应被允许 (系统场景 ID 可为中文)。"""

    def test_chinese_scene_id_allowed(self, photo_service):
        album = photo_service.create_album("采集场景", "抓取集")
        assert album["name"] == "抓取集"
        photo = photo_service.save_photo("采集场景", album["id"], _jpeg_bytes())
        assert photo_service.get_photo_path("采集场景", album["id"], photo["id"]).is_file()
        # list 回路正常
        albums = photo_service.list_albums("采集场景")
        assert len(albums) == 1


class TestCascade:
    def test_delete_scene_photos_removes_albums(self, photo_service):
        album = photo_service.create_album("scene_a", "集")
        photo_service.save_photo("scene_a", album["id"], _jpeg_bytes())
        assert photo_service.delete_scene_photos("scene_a") is True
        # 再次删除返回 False (目录已不存在)
        assert photo_service.delete_scene_photos("scene_a") is False
        assert photo_service.list_albums("scene_a") == []

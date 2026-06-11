"""
WebSocket 相机推流处理器。

挂载到 robot_control FastAPI 的 /ws/v1/camera 端点。
从 camera_manager 获取最新帧，编码为 JPEG base64 推送给前端。

协议:
  前端 → 服务端: {"action": "subscribe", "camera_id": "head", "stream_type": "raw"}
  服务端 → 前端: {"type": "frame", "camera_id": "head", "stream_type": "raw", "data": "<base64>"}
  服务端 → 前端: {"type": "error", "message": "..."}
  前端 → 服务端: {"action": "unsubscribe"}
"""

import asyncio
import base64
import json
import logging
import time

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# 深度渲染配置
MIN_DEPTH_MM = 100
MAX_DEPTH_MM = 5000


def _render_depth_3d(depth_mm: np.ndarray) -> np.ndarray:
    """将 float32 深度图渲染为 3D 浮雕 BGR 图像。"""
    depth_clipped = np.clip(depth_mm, MIN_DEPTH_MM, MAX_DEPTH_MM)
    depth_norm = (depth_clipped - MIN_DEPTH_MM) / (MAX_DEPTH_MM - MIN_DEPTH_MM + 1e-6)
    depth_gamma = np.power(depth_norm, 0.8)
    depth_8bit = (depth_gamma * 255).astype(np.uint8)

    grad_x = cv2.Scharr(depth_8bit, cv2.CV_32F, 1, 0)
    grad_y = cv2.Scharr(depth_8bit, cv2.CV_32F, 0, 1)
    mag = cv2.magnitude(grad_x, grad_y) + 1.0

    lighting = -0.707 * (grad_x + grad_y) / mag
    lighting = lighting * 0.15 + 0.85
    np.clip(lighting, 0.7, 1.0, out=lighting)

    depth_colored = cv2.applyColorMap(depth_8bit, cv2.COLORMAP_JET)
    depth_colored = (depth_colored * lighting[..., np.newaxis]).astype(np.uint8)
    return depth_colored


def _frame_to_jpeg_base64(frame: np.ndarray) -> str:
    """将 numpy 图像编码为 JPEG base64 字符串。"""
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(jpeg.tobytes()).decode("ascii")


@router.websocket("/ws/v1/camera")
async def camera_websocket(websocket: WebSocket):
    """相机视频推流 WebSocket 端点。"""
    from python_pkgs.vision.camera_manager import get_camera_manager

    await websocket.accept()

    camera_id: str | None = None
    stream_type: str = "raw"
    push_task: asyncio.Task | None = None

    async def push_frames():
        """后台协程: 从 camera_manager 获取帧并推送。"""
        manager = get_camera_manager()
        if manager is None:
            await websocket.send_json({"type": "error", "message": "CameraManager not initialized"})
            return

        last_ts = 0.0
        fps = 15
        if camera_id:
            for cam in manager.get_camera_list():
                if cam["id"] == camera_id:
                    fps = max(cam.get("color_fps", 15), 15)
                    break
        interval = 1.0 / fps

        while True:
            try:
                if camera_id is None:
                    await asyncio.sleep(0.1)
                    continue

                ts = manager.get_frame_timestamp(camera_id)
                if ts == last_ts:
                    await asyncio.sleep(0.01)
                    continue
                last_ts = ts

                if stream_type == "depth":
                    frame = manager.get_latest_depth(camera_id)
                    if frame is not None:
                        frame = _render_depth_3d(frame)
                else:
                    frame = manager.get_latest_color(camera_id)

                if frame is None:
                    await asyncio.sleep(0.01)
                    continue

                jpeg_b64 = _frame_to_jpeg_base64(frame)
                await websocket.send_json({
                    "type": "frame",
                    "camera_id": camera_id,
                    "stream_type": stream_type,
                    "data": jpeg_b64,
                })

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Push error for %s", camera_id)
                await asyncio.sleep(0.1)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action", "")

            if action == "subscribe":
                camera_id = msg.get("camera_id", "")
                stream_type = msg.get("stream_type", "raw")

                manager = get_camera_manager()
                if manager is None:
                    await websocket.send_json({"type": "error", "message": "CameraManager not initialized"})
                    continue

                cam_list = [c["id"] for c in manager.get_camera_list()]
                if camera_id not in cam_list:
                    await websocket.send_json({"type": "error", "message": f"Camera not found: {camera_id}"})
                    continue

                if not manager.is_streaming(camera_id):
                    result = manager.start_stream(camera_id)
                    if not result["success"]:
                        await websocket.send_json({"type": "error", "message": result["message"]})
                        continue

                if push_task:
                    push_task.cancel()
                push_task = asyncio.create_task(push_frames())
                logger.info("WS subscribe: camera=%s, stream_type=%s", camera_id, stream_type)

            elif action == "unsubscribe":
                if push_task:
                    push_task.cancel()
                    push_task = None
                camera_id = None
                logger.info("WS unsubscribe")

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        logger.info("WS disconnected: camera=%s", camera_id)
    finally:
        if push_task:
            push_task.cancel()

"""
WebSocket 相机推流转发器。

挂载到 /ws/v1/camera。接收前端的订阅请求，转发到
camera_manager_node 的内部 WebSocket (localhost:8766)，
将帧数据透传给前端。
"""

import asyncio
import logging

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

CAMERA_WS_URL = "ws://127.0.0.1:8766"


@router.websocket("/ws/v1/camera")
async def camera_relay(ws: WebSocket):
    await ws.accept()

    upstream: websockets.WebSocketClientProtocol | None = None
    relay_task: asyncio.Task | None = None

    async def relay_upstream_to_frontend():
        try:
            while upstream is not None:
                try:
                    msg = await asyncio.wait_for(upstream.recv(), timeout=30.0)
                    await ws.send_text(msg)
                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    break
        except Exception:
            pass

    async def connect_upstream() -> bool:
        nonlocal upstream
        try:
            upstream = await websockets.connect(CAMERA_WS_URL)
            return True
        except (ConnectionRefusedError, OSError) as e:
            logger.warning("Camera WS upstream not available (%s): %s", CAMERA_WS_URL, e)
            await ws.send_json({"type": "error", "message": "相机服务未启动，请先通过节点管理启动 camera_manager"})
            return False

    try:
        while True:
            raw = await ws.receive_text()

            # 懒连接: 收到第一条消息时才连 camera_manager_node
            if upstream is None or not upstream.open:
                if not await connect_upstream():
                    continue
                if relay_task:
                    relay_task.cancel()
                relay_task = asyncio.create_task(relay_upstream_to_frontend())

            await upstream.send(raw)

    except WebSocketDisconnect:
        logger.info("Camera WS relay: frontend disconnected")
    except Exception:
        logger.exception("Camera WS relay error")
    finally:
        if relay_task:
            relay_task.cancel()
        if upstream and upstream.open:
            await upstream.close()

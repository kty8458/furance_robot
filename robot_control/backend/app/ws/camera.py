"""
WebSocket 相机推流转发器。

挂载到 /ws/v1/camera。接收前端的订阅请求，转发到
camera_manager_node 的内部 WebSocket (localhost:8766)。
"""

import asyncio
import logging

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()
CAMERA_WS_URL = "ws://127.0.0.1:8766"


def _is_open(conn) -> bool:
    """检查 websockets 连接是否开启 (兼容 v15+ 无 .open 属性)。"""
    return conn is not None and conn.state.name == "OPEN"


@router.websocket("/ws/v1/camera")
async def camera_relay(ws: WebSocket):
    await ws.accept()

    upstream = None
    relay_task = None

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

    async def connect_upstream():
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

            if not _is_open(upstream):
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
        if _is_open(upstream):
            await upstream.close()

import logging
from app.clients.l2_client import L2ClientBase, DefaultL2Client
from app.core.config import get_settings

logger = logging.getLogger("dispatch.l2")


class L2Listener:
    def __init__(self, client: L2ClientBase | None = None):
        settings = get_settings()
        self._enabled = settings.l2.enabled
        self._client = client or DefaultL2Client()
        self._running = False

    async def start(self):
        if not self._enabled:
            logger.info("L2 listener disabled")
            return
        self._running = True
        await self._client.connect()
        logger.info("L2 listener started")
        async for cmd in self._client.listen():
            if not self._running:
                break
            await self._on_command(cmd)

    async def stop(self):
        self._running = False
        await self._client.disconnect()
        logger.info("L2 listener stopped")

    async def _on_command(self, cmd: dict):
        logger.info(f"L2 command received: {cmd}")
        # TODO: implement when L2 protocol is defined
        # 1. Parse command → extract task_template_id + params
        # 2. Find matching template
        # 3. Call TaskEngine.execute()
        # 4. Record to l2_commands table
        # 5. Send response back via L2Client
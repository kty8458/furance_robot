import os
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from furance_shared.protocol.http_schema import ApiResponse
from app.main import create_app
from app.core.database import Database


@pytest.fixture
def mock_robot_proxy():
    proxy = AsyncMock()
    proxy.forward = AsyncMock(return_value=ApiResponse(code=0, data={"success": True}))
    proxy.forward_get = AsyncMock(return_value=ApiResponse(code=0, data={}))
    return proxy


@pytest.fixture
def app(tmp_path):
    """Create app with test database, manually setting app.state as lifespan won't run."""
    os.environ["DATABASE_PATH"] = str(tmp_path / "test.db")
    application = create_app()

    # Manually init DB since httpx ASGITransport doesn't trigger lifespan
    db = Database(str(tmp_path / "test.db"))

    async def _init_db():
        await db.init()
        application.state.db = db

    # Run init synchronously via import trick
    import asyncio
    asyncio.get_event_loop().run_until_complete(_init_db())

    yield application

    async def _close_db():
        await db.close()

    asyncio.get_event_loop().run_until_complete(_close_db())
    os.environ.pop("DATABASE_PATH", None)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "unit_test.db"))
    await database.init()
    yield database
    await database.close()

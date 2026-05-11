from abc import ABC, abstractmethod
from typing import Any


class Ros2ServiceClientBase(ABC):
    @abstractmethod
    async def call_service(self, service_name: str, request: dict[str, Any]) -> dict[str, Any]:
        ...


class MockRos2ServiceClient(Ros2ServiceClientBase):
    async def call_service(self, service_name: str, request: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "message": "ok"}

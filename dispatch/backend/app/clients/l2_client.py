from abc import ABC, abstractmethod
from typing import AsyncIterator


class L2ClientBase(ABC):
    @abstractmethod
    async def connect(self):
        ...

    @abstractmethod
    async def disconnect(self):
        ...

    @abstractmethod
    async def listen(self) -> AsyncIterator[dict]:
        ...

    @abstractmethod
    async def send_response(self, request_id: str, result: dict):
        ...


class DefaultL2Client(L2ClientBase):
    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def listen(self) -> AsyncIterator[dict]:
        return
        yield  # make it an async generator

    async def send_response(self, request_id: str, result: dict):
        pass
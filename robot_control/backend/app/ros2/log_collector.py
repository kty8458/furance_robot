from abc import ABC, abstractmethod
from app.services.log_service import LogService


class Ros2LogCollectorBase(ABC):
    @abstractmethod
    async def start(self, log_service: LogService):
        ...

    @abstractmethod
    async def stop(self):
        ...


class MockRos2LogCollector(Ros2LogCollectorBase):
    async def start(self, log_service: LogService):
        pass

    async def stop(self):
        pass

from furance_shared.utils.enum import StrEnum


class TaskStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class NodeStatus(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class SamplerStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    COMPLETED = "completed"

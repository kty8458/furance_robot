from pydantic import BaseModel, Field
from furance_shared.utils.enum import StrEnum
from typing import Optional


class AlarmLevel(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


class AlarmSource(StrEnum):
    ROBOT = "robot"
    SAMPLER = "sampler"
    DISPATCH = "dispatch"


class AlarmAckStatus(StrEnum):
    UNACK = "unack"
    ACKED = "acked"


class AlarmRuleCondition(BaseModel):
    field: str
    operator: str = "<"
    value: float


class AlarmRule(BaseModel):
    id: Optional[int] = None
    name: str
    category: str
    level: AlarmLevel
    condition_json: dict
    enabled: bool = True

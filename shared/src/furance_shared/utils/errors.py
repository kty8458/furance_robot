from enum import IntEnum


class ErrorCode(IntEnum):
    # 通讯类 1xxx
    ROS2_TIMEOUT = 1001
    WS_DISCONNECTED = 1002
    HTTP_REQUEST_FAILED = 1003

    # 硬件类 2xxx
    MOVE_FAILED = 2001
    GRIPPER_ERROR = 2002
    LIFT_ERROR = 2003
    ARM_ERROR = 2004
    CHARGE_ERROR = 2005

    # 业务类 3xxx
    TASK_CONFLICT = 3001
    INVALID_PARAMS = 3002
    NODE_NOT_FOUND = 3003
    TEACH_NAME_EXISTS = 3004
    TEACH_NAME_NOT_FOUND = 3005

    # 工序类 4xxx
    WORKFLOW_NOT_FOUND = 4001
    WORKFLOW_NAME_EXISTS = 4002
    WORKFLOW_STEP_FAILED = 4003


class FuranceError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")

    def to_dict(self) -> dict:
        return {"code": int(self.code), "message": self.message}


class CommError(FuranceError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.ROS2_TIMEOUT):
        super().__init__(code=code, message=message)


class HardwareError(FuranceError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.MOVE_FAILED):
        super().__init__(code=code, message=message)


class BusinessError(FuranceError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.TASK_CONFLICT):
        super().__init__(code=code, message=message)

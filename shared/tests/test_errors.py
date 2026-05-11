import pytest

from furance_shared.utils.errors import (
    ErrorCode,
    FuranceError,
    CommError,
    HardwareError,
    BusinessError,
)


def test_error_code_ranges():
    assert ErrorCode.ROS2_TIMEOUT >= 1000
    assert ErrorCode.ROS2_TIMEOUT < 2000
    assert ErrorCode.MOVE_FAILED >= 2000
    assert ErrorCode.MOVE_FAILED < 3000
    assert ErrorCode.TASK_CONFLICT >= 3000
    assert ErrorCode.TASK_CONFLICT < 4000


def test_furance_error_fields():
    err = FuranceError(code=ErrorCode.ROS2_TIMEOUT, message="timeout")
    assert err.code == 1001
    assert err.message == "timeout"


def test_comm_error():
    err = CommError(message="ws disconnected")
    assert err.code >= 1000
    assert err.code < 2000


def test_hardware_error():
    err = HardwareError(message="move failed")
    assert err.code >= 2000
    assert err.code < 3000


def test_business_error():
    err = BusinessError(message="task conflict")
    assert err.code >= 3000
    assert err.code < 4000


def test_error_to_dict():
    err = FuranceError(code=ErrorCode.ROS2_TIMEOUT, message="timeout")
    d = err.to_dict()
    assert d == {"code": 1001, "message": "timeout"}

from furance_shared.protocol.http_schema import ApiResponse, ErrorResponse


def test_api_response_success():
    resp = ApiResponse(data={"task_id": "123"})
    assert resp.code == 0
    assert resp.message == "ok"
    assert resp.data == {"task_id": "123"}


def test_api_response_custom_message():
    resp = ApiResponse(code=0, message="created", data=None)
    assert resp.message == "created"
    assert resp.data is None


def test_error_response():
    resp = ErrorResponse(code=1001, message="ROS2 timeout")
    assert resp.code == 1001
    assert resp.data is None

"""Tests for app.ros2.moveit_client.

Covers MockMoveItServiceClient behavior and RealMoveItServiceClient request
construction (without a live ROS2 stack — service clients are stubbed).
"""

import asyncio
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from app.ros2.moveit_client import (
    MockMoveItServiceClient,
    RealMoveItServiceClient,
    LEFT_JOINT_NAMES,
    RIGHT_JOINT_NAMES,
)


# -------- Mock client --------

@pytest.mark.asyncio
async def test_mock_move_p_ok():
    client = MockMoveItServiceClient()
    res = await client.move_p("left", {"x": 0.3}, "ARM-L-J7_Link", "base_link", "ompl")
    assert res["success"] is True
    assert "MoveP" in res["message"]


@pytest.mark.asyncio
async def test_mock_move_l_ok():
    client = MockMoveItServiceClient()
    res = await client.move_l("right", [{"x": 0.1}, {"x": 0.2}])
    assert res["success"] is True


@pytest.mark.asyncio
async def test_mock_move_j_ok():
    client = MockMoveItServiceClient()
    res = await client.move_j("left", [0.0] * 7)
    assert res["success"] is True


@pytest.mark.asyncio
async def test_mock_move_j_wrong_dimension():
    client = MockMoveItServiceClient()
    res = await client.move_j("left", [0.0] * 5)
    assert res["success"] is False
    assert "7" in res["message"]


# -------- Real client request construction --------

@pytest.fixture
def fake_runtime():
    runtime = MagicMock()
    runtime.node = MagicMock()
    return runtime


def _install_fake_msg_modules():
    """Inject minimal stand-ins for ROS2 msg/srv types so the real client
    can be exercised without a ROS2 install."""
    modules = {}

    # control_interfaces.srv
    ci_srv = types.ModuleType("control_interfaces.srv")

    class _Req:
        def __init__(self):
            self.lor = ""
            self.to_frame = ""
            self.reference_frame = ""
            self.planner = ""
            self.target_pose = None
            self.waypoints = []
            self.trajectory = None

    class MoveP:
        Request = _Req

    class MoveL:
        Request = _Req

    class ExecuteTrajectory:
        Request = _Req

    ci_srv.MoveP = MoveP
    ci_srv.MoveL = MoveL
    ci_srv.ExecuteTrajectory = ExecuteTrajectory
    modules["control_interfaces"] = types.ModuleType("control_interfaces")
    modules["control_interfaces.srv"] = ci_srv

    # geometry_msgs.msg
    gm = types.ModuleType("geometry_msgs.msg")

    class _Point:
        def __init__(self):
            self.x = self.y = self.z = 0.0

    class _Quat:
        def __init__(self):
            self.x = self.y = self.z = 0.0
            self.w = 1.0

    class Pose:
        def __init__(self):
            self.position = _Point()
            self.orientation = _Quat()

    class _Header:
        def __init__(self):
            self.frame_id = ""

    class PoseStamped:
        def __init__(self):
            self.header = _Header()
            self.pose = Pose()

    gm.Pose = Pose
    gm.PoseStamped = PoseStamped
    modules["geometry_msgs"] = types.ModuleType("geometry_msgs")
    modules["geometry_msgs.msg"] = gm

    # trajectory_msgs.msg
    tm = types.ModuleType("trajectory_msgs.msg")

    class JointTrajectoryPoint:
        def __init__(self):
            self.positions = []
            self.time_from_start = None

    class JointTrajectory:
        def __init__(self):
            self.joint_names = []
            self.points = []

    tm.JointTrajectory = JointTrajectory
    tm.JointTrajectoryPoint = JointTrajectoryPoint
    modules["trajectory_msgs"] = types.ModuleType("trajectory_msgs")
    modules["trajectory_msgs.msg"] = tm

    # builtin_interfaces.msg
    bi = types.ModuleType("builtin_interfaces.msg")

    class Duration:
        def __init__(self):
            self.sec = 0
            self.nanosec = 0

    bi.Duration = Duration
    modules["builtin_interfaces"] = types.ModuleType("builtin_interfaces")
    modules["builtin_interfaces.msg"] = bi

    return modules


@pytest.fixture
def fake_ros_modules(monkeypatch):
    modules = _install_fake_msg_modules()
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return modules


def _patch_real_client_with_stub_service(client, captured: dict):
    """Replace the underlying ROS2 client with one that captures the request."""
    stub = MagicMock()
    stub.wait_for_service.return_value = True

    def call_async(req):
        captured["req"] = req
        fut = MagicMock()

        def add_done_callback(cb):
            response = MagicMock()
            response.success = True
            response.message = "stub ok"
            done = MagicMock()
            done.result.return_value = response
            cb(done)

        fut.add_done_callback.side_effect = add_done_callback
        return fut

    stub.call_async.side_effect = call_async
    client._get_or_create_client = MagicMock(return_value=stub)


@pytest.mark.asyncio
async def test_real_move_p_request_fields(fake_runtime, fake_ros_modules):
    # Force HAS_RCLPY=True so constructor doesn't reject
    with patch("app.ros2.moveit_client.HAS_RCLPY", True):
        client = RealMoveItServiceClient(fake_runtime, timeout=2.0)

    captured = {}
    _patch_real_client_with_stub_service(client, captured)

    res = await client.move_p(
        lor="left",
        target_pose={"x": 0.3, "y": 0.1, "z": 0.4, "qw": 1.0},
        to_frame="ARM-L-J7_Link",
        reference_frame="base_link",
        planner="ompl",
    )
    assert res["success"] is True
    req = captured["req"]
    assert req.lor == "left"
    assert req.to_frame == "ARM-L-J7_Link"
    assert req.reference_frame == "base_link"
    assert req.planner == "ompl"
    assert req.target_pose.pose.position.x == 0.3
    assert req.target_pose.pose.orientation.w == 1.0


@pytest.mark.asyncio
async def test_real_move_l_request_fields(fake_runtime, fake_ros_modules):
    with patch("app.ros2.moveit_client.HAS_RCLPY", True):
        client = RealMoveItServiceClient(fake_runtime, timeout=2.0)

    captured = {}
    _patch_real_client_with_stub_service(client, captured)

    res = await client.move_l(
        lor="right",
        waypoints=[
            {"x": 0.1, "y": 0.0, "z": 0.2, "qw": 1.0},
            {"x": 0.2, "y": 0.0, "z": 0.2, "qw": 1.0},
        ],
    )
    assert res["success"] is True
    req = captured["req"]
    assert req.lor == "right"
    assert len(req.waypoints) == 2
    assert req.waypoints[0].position.x == 0.1
    assert req.waypoints[1].position.x == 0.2


@pytest.mark.asyncio
async def test_real_move_j_uses_left_joint_names(fake_runtime, fake_ros_modules):
    with patch("app.ros2.moveit_client.HAS_RCLPY", True):
        client = RealMoveItServiceClient(fake_runtime, timeout=2.0)

    captured = {}
    _patch_real_client_with_stub_service(client, captured)
    # Prime cached joint state so move_j has a valid start point.
    for n in LEFT_JOINT_NAMES:
        client._joint_positions[n] = 0.0
    client._joint_state_sub = object()  # skip subscription creation

    res = await client.move_j(lor="left", joint_positions=[180.0] * 7, duration=2.5)
    assert res["success"] is True
    req = captured["req"]
    assert req.trajectory.joint_names == LEFT_JOINT_NAMES
    assert len(req.trajectory.points) == 2
    # First point is the current state (radians, time=0).
    import math
    assert req.trajectory.points[0].positions == [0.0] * 7
    assert req.trajectory.points[0].time_from_start.sec == 0
    assert req.trajectory.points[0].time_from_start.nanosec == 0
    # Second point is the target (deg -> rad).
    assert req.trajectory.points[1].positions == pytest.approx([math.pi] * 7)
    assert req.trajectory.points[1].time_from_start.sec == 2
    assert req.trajectory.points[1].time_from_start.nanosec == int(0.5 * 1e9)


@pytest.mark.asyncio
async def test_real_move_j_uses_right_joint_names(fake_runtime, fake_ros_modules):
    with patch("app.ros2.moveit_client.HAS_RCLPY", True):
        client = RealMoveItServiceClient(fake_runtime, timeout=2.0)
    captured = {}
    _patch_real_client_with_stub_service(client, captured)
    for n in RIGHT_JOINT_NAMES:
        client._joint_positions[n] = 0.0
    client._joint_state_sub = object()
    await client.move_j(lor="right", joint_positions=[0.0] * 7)
    assert captured["req"].trajectory.joint_names == RIGHT_JOINT_NAMES


@pytest.mark.asyncio
async def test_real_move_j_rejects_bad_dimension(fake_runtime, fake_ros_modules):
    with patch("app.ros2.moveit_client.HAS_RCLPY", True):
        client = RealMoveItServiceClient(fake_runtime, timeout=2.0)
    res = await client.move_j(lor="left", joint_positions=[0.0] * 6)
    assert res["success"] is False


@pytest.mark.asyncio
async def test_real_client_service_unavailable(fake_runtime, fake_ros_modules):
    with patch("app.ros2.moveit_client.HAS_RCLPY", True):
        client = RealMoveItServiceClient(fake_runtime, timeout=2.0)
    stub = MagicMock()
    stub.wait_for_service.return_value = False
    client._get_or_create_client = MagicMock(return_value=stub)

    res = await client.move_j("left", [0.0] * 7)
    assert res["success"] is False
    assert "not available" in res["message"]

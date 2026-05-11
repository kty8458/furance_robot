from app.core.config import Settings


def test_default_settings():
    s = Settings()
    assert s.server_host == "0.0.0.0"
    assert s.server_port == 8000
    assert s.l2.enabled is False
    assert s.l2.adapter == "default"


def test_robot_configs():
    s = Settings()
    assert len(s.robots) > 0
    assert s.robots[0].id == "robot_001"
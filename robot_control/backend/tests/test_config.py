import pytest
from app.core.config import Settings


def test_default_settings():
    s = Settings()
    assert s.server_host == "0.0.0.0"
    assert s.server_port == 8000
    assert s.ros2_domain_id == 0
    assert s.ros2_service_timeout == 30.0
    assert s.ws_status_interval == 30
    assert s.log_level == "INFO"
    assert s.log_retention_days == 30


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.server_port == 9000
    assert s.log_level == "DEBUG"

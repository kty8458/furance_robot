from pydantic_settings import BaseSettings
from pydantic import Field
import os


class Settings(BaseSettings):
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    ros2_domain_id: int = Field(default_factory=lambda: int(os.environ.get("ROS_DOMAIN_ID", "0")))
    ros2_service_timeout: float = 30.0

    ws_status_interval: int = 30

    log_level: str = "INFO"
    log_dir: str = "data/logs"
    log_retention_days: int = 0  # 0 = no auto cleanup

    teach_data_dir: str = "data/teach"
    workflow_data_dir: str = "data/workflows"
    photo_data_dir: str = "data/photos"

    chassis_base_url: str = "http://192.168.1.102:8888/yhs-robot"
    chassis_user_code: str = "admin"
    chassis_password: str = "admin123"
    chassis_timeout: float = 15.0

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    return Settings()

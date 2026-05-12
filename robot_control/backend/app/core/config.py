from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    ros2_domain_id: int = 0
    ros2_service_timeout: float = 30.0

    ws_status_interval: int = 30

    log_level: str = "INFO"
    log_dir: str = "data/logs"
    log_retention_days: int = 30

    teach_data_dir: str = "data/teach"

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    return Settings()

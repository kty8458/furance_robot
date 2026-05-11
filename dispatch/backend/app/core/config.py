from pydantic import BaseModel
from pydantic_settings import BaseSettings


class RobotConfig(BaseModel):
    id: str
    name: str
    control_url: str
    ws_url: str


class SamplerConfig(BaseModel):
    ws_url: str


class L2Config(BaseModel):
    enabled: bool = False
    adapter: str = "default"


class Settings(BaseSettings):
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    robots: list[RobotConfig] = [
        RobotConfig(
            id="robot_001",
            name="1号机器人",
            control_url="http://192.168.1.100:8000",
            ws_url="ws://192.168.1.100:8000/ws/v1/status",
        )
    ]

    sampler: SamplerConfig = SamplerConfig(ws_url="ws://192.168.1.200:9000")

    l2: L2Config = L2Config()

    database_path: str = "./data/dispatch.db"

    log_level: str = "INFO"
    log_dir: str = "C:\\FuranceDispatch\\logs"
    log_retention_days: int = 30

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    return Settings()
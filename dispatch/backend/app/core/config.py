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
            control_url="http://127.0.0.1:9001",
            ws_url="ws://127.0.0.1:9001/ws/v1/status",
        )
    ]

    sampler: SamplerConfig = SamplerConfig(ws_url="ws://127.0.0.1:9002/ws")

    l2: L2Config = L2Config()

    database_path: str = "./data/dispatch.db"

    log_level: str = "INFO"
    log_dir: str = "C:\\FuranceDispatch\\logs"
    log_retention_days: int = 30

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    return Settings()
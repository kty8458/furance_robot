"""Robot Control System entry point for PyInstaller deployment."""
import os
import sys
import yaml
import uvicorn
from pathlib import Path


def main():
    base_dir = Path(__file__).parent
    config_path = base_dir / "config" / "config.yaml"

    host = "0.0.0.0"
    port = 8000
    log_level = "info"

    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
        server_cfg = config.get("server", {})
        host = server_cfg.get("host", host)
        port = server_cfg.get("port", port)
        log_level = config.get("logging", {}).get("level", "info").lower()

    static_dir = str(base_dir / "static")
    os.environ["STATIC_DIR"] = static_dir
    os.environ["TEACH_DATA_DIR"] = str(base_dir / "data" / "teach")
    os.environ["LOG_DIR"] = str(base_dir / "logs")

    sys.path.insert(0, str(base_dir / "bin"))

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()

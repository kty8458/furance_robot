import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(name: str, level: str = "INFO", log_dir: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_path / f"{name}.log",
            when="midnight",
            backupCount=30,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

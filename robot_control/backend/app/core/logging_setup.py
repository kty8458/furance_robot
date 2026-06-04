"""Configure root logger with daily file handler.

Output goes to:
- stdout (existing behavior)
- ``<log_dir>/control_system_backend-YYYY-MM-DD.log`` (one file per day)

A startup-time cleanup deletes files older than ``log_retention_days``.

Rather than relying on ``TimedRotatingFileHandler``'s mid-process rollover
(which complicates the file naming), each backend run writes to the file
named for the current local date at startup. Long-running processes spanning
midnight will keep writing to the old date's file — acceptable trade-off
given that we expect operators to restart the backend regularly.
"""
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

LOG_FORMAT = "[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
FILE_PREFIX = "control_system_backend"

# Third-party loggers that flood the file at INFO level. Pin to WARNING so
# only real failures show up.
_NOISY_LOGGERS = {
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "uvicorn.access": "WARNING",
    "asyncio": "WARNING",
    "watchfiles": "WARNING",
    "websockets": "WARNING",
    "multipart": "WARNING",
    "PIL": "WARNING",
}

_FILE_PATTERN = re.compile(rf"^{FILE_PREFIX}-(\d{{4}}-\d{{2}}-\d{{2}})\.log$")


def setup_file_logging(log_dir: str, level: str = "INFO", retention_days: int = 0) -> None:
    """Attach a daily file handler to the root logger.

    Idempotent: a marker on the handler prevents double-attach on lifespan
    re-entry (tests, hot reload).
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    for h in root.handlers:
        if getattr(h, "_furance_file_log", False):
            return

    today_file = log_path / f"{FILE_PREFIX}-{datetime.now():%Y-%m-%d}.log"
    handler = logging.FileHandler(filename=str(today_file), encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    handler.setLevel(level)
    handler._furance_file_log = True
    root.addHandler(handler)

    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )
    if not has_stream:
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
        stream.setLevel(level)
        root.addHandler(stream)

    if retention_days and retention_days > 0:
        _cleanup_old_logs(log_path, retention_days)

    # Quiet noisy third-party loggers that drown business events at INFO level.
    for name, level_name in _NOISY_LOGGERS.items():
        logging.getLogger(name).setLevel(level_name)


def _cleanup_old_logs(log_dir: Path, retention_days: int) -> None:
    """Delete control_system_backend-*.log files older than retention_days."""
    cutoff = datetime.now() - timedelta(days=retention_days)
    for entry in log_dir.iterdir():
        if not entry.is_file():
            continue
        m = _FILE_PATTERN.match(entry.name)
        if not m:
            continue
        try:
            file_date = datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                entry.unlink()
            except OSError:
                pass


def list_backend_log_dates(log_dir: str) -> list[str]:
    """Return sorted (desc) list of available backend log dates as YYYY-MM-DD."""
    p = Path(log_dir)
    if not p.is_dir():
        return []
    dates = []
    for entry in p.iterdir():
        if not entry.is_file():
            continue
        m = _FILE_PATTERN.match(entry.name)
        if m:
            dates.append(m.group(1))
    return sorted(dates, reverse=True)


def backend_log_path(log_dir: str, date: str) -> Path:
    """Return the path for a given backend log date (no existence check)."""
    return Path(log_dir) / f"{FILE_PREFIX}-{date}.log"

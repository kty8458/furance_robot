"""HTTP endpoints for backend and ROS2 node log viewing/download.

Routes (prefix /api/v1/system/logs):
  GET  /backend                              list dates
  GET  /backend/{date}                       view content (?tail=N)
  GET  /backend/{date}/download              download file
  GET  /ros2-nodes                           list dates + nodes per date
  GET  /ros2-nodes/{date}                    view all nodes content
  GET  /ros2-nodes/{node}/{date}/download    download single node log
"""
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from furance_shared.protocol.http_schema import ApiResponse
from app.core.config import get_settings
from app.core.logging_setup import (
    FILE_PREFIX,
    backend_log_path,
    list_backend_log_dates,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system/logs", tags=["system-logs"])

ROS2_LOG_BASE_DIR = Path(os.path.expanduser("~")) / ".ros" / "node_manager_logs"
_SESSION_DATE_PATTERN = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})")


# ---- helpers ----

def _read_tail(path: Path, tail: int | None) -> tuple[list[str], int]:
    """Return (lines, total_lines). tail=None returns the whole file."""
    if not path.is_file():
        return [], 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            all_lines = [line.rstrip("\n") for line in f]
    except OSError as exc:
        logger.error("Failed to read log %s: %s", path, exc)
        return [], 0
    total = len(all_lines)
    if tail and tail > 0 and tail < total:
        return all_lines[-tail:], total
    return all_lines, total


def _session_date(session_name: str) -> str | None:
    """Extract YYYY-MM-DD from a ros2 session directory name."""
    m = _SESSION_DATE_PATTERN.search(session_name)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _sessions_by_date() -> dict[str, list[Path]]:
    """Group ros2 session directories by their date stamp."""
    grouped: dict[str, list[Path]] = {}
    if not ROS2_LOG_BASE_DIR.is_dir():
        return grouped
    for entry in ROS2_LOG_BASE_DIR.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        date = _session_date(entry.name)
        if not date:
            continue
        grouped.setdefault(date, []).append(entry)
    return grouped


def _node_files_for_date(date: str) -> list[Path]:
    """Return all node .log files across sessions belonging to a given date."""
    sessions = _sessions_by_date().get(date, [])
    files = []
    for sess in sessions:
        for f in sess.iterdir():
            if f.is_file() and f.suffix == ".log":
                files.append(f)
    return files


# ---- backend log endpoints ----

@router.get("/backend", response_model=ApiResponse)
async def list_backend_logs():
    settings = get_settings()
    dates = list_backend_log_dates(settings.log_dir)
    return ApiResponse(data={"dates": dates})


@router.get("/backend/{date}", response_model=ApiResponse)
async def view_backend_log(date: str, tail: int | None = Query(None, ge=1)):
    settings = get_settings()
    path = backend_log_path(settings.log_dir, date)
    if not path.is_file():
        return ApiResponse(code=3002, message=f"日志文件不存在: {path.name}")
    lines, total = _read_tail(path, tail)
    return ApiResponse(data={"date": date, "lines": lines, "total": total})


@router.get("/backend/{date}/download")
async def download_backend_log(date: str):
    settings = get_settings()
    path = backend_log_path(settings.log_dir, date)
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": 3002, "message": "日志文件不存在"})
    return FileResponse(
        path=str(path), media_type="text/plain", filename=path.name,
    )


# ---- ROS2 node log endpoints ----

@router.get("/ros2-nodes", response_model=ApiResponse)
async def list_ros2_dates():
    grouped = _sessions_by_date()
    dates_info = []
    for date in sorted(grouped.keys(), reverse=True):
        node_names = set()
        for sess in grouped[date]:
            for f in sess.iterdir():
                if f.is_file() and f.suffix == ".log":
                    node_names.add(f.stem)
        dates_info.append({"date": date, "nodes": sorted(node_names)})
    return ApiResponse(data={"dates": dates_info})


@router.get("/ros2-nodes/{date}", response_model=ApiResponse)
async def view_ros2_logs(date: str, tail: int | None = Query(None, ge=1)):
    files = _node_files_for_date(date)
    if not files:
        return ApiResponse(code=3002, message=f"{date} 没有 ROS2 节点日志")
    segments = []
    total = 0
    for f in sorted(files):
        lines, count = _read_tail(f, tail)
        segments.append({"node": f.stem, "session": f.parent.name, "lines": lines, "total": count})
        total += count
    return ApiResponse(data={"date": date, "segments": segments, "total": total})


@router.get("/ros2-nodes/{node}/{date}/download")
async def download_ros2_node_log(node: str, date: str):
    sessions = _sessions_by_date().get(date, [])
    for sess in sessions:
        path = sess / f"{node}.log"
        if path.is_file():
            return FileResponse(
                path=str(path), media_type="text/plain",
                filename=f"{node}-{date}.log",
            )
    raise HTTPException(status_code=404, detail={"code": 3002, "message": "日志文件不存在"})


__all__ = ["router", "FILE_PREFIX"]

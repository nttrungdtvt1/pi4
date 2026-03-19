# logging_module/log_formatter.py
"""
Utility đọc và format lại file log để hiển thị hoặc export.
Dùng bởi log_server.py và API Endpoint cho Web Dashboard.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Generator, Any

from logging_module.event_logger import get_log_paths


def iter_log_entries(log_type: str = "events") -> Generator[dict[str, Any], None, None]:
    """Generator đọc từng dòng JSON từ file log (Lazy loading tiết kiệm RAM)."""
    paths = get_log_paths()
    path = paths.get(log_type)

    if not path or not path.exists():
        return

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Bỏ qua các dòng bị hỏng (corrupted) do mất điện đột ngột
                continue


def filter_entries(
    log_type: str = "events",
    event_types: list[str] | None = None,
    start_ts: str | None = None,
    end_ts:   str | None = None,
    limit:    int = 500,
) -> list[dict[str, Any]]:
    """Đọc và lọc log entries theo các điều kiện truy vấn."""
    start_dt = datetime.fromisoformat(start_ts) if start_ts else None
    end_dt   = datetime.fromisoformat(end_ts)   if end_ts   else None

    results = []
    for entry in iter_log_entries(log_type):
        # Lọc theo loại sự kiện
        if event_types and entry.get("event") not in event_types:
            continue

        # Lọc theo khoảng thời gian
        if start_dt or end_dt:
            try:
                entry_dt = datetime.fromisoformat(entry["ts"])
                if start_dt and entry_dt < start_dt:
                    continue
                if end_dt and entry_dt > end_dt:
                    continue
            except (KeyError, ValueError):
                continue # Bỏ qua entry nếu timestamp không hợp lệ

        results.append(entry)

        # Ngắt sớm nếu đã đủ số lượng limit để tiết kiệm CPU
        if len(results) >= limit:
            break

    return results


def format_summary(log_type: str = "events") -> dict[str, Any]:
    """Thống kê nhanh file log dùng cho Dashboard Health Check."""
    total = 0
    first_ts = None
    last_ts  = None
    event_counts: dict[str, int] = {}

    for entry in iter_log_entries(log_type):
        total += 1
        ts = entry.get("ts", "")

        if ts:
            if first_ts is None:
                first_ts = ts # Dòng đầu tiên hợp lệ
            last_ts = ts      # Cập nhật liên tục để lấy dòng cuối cùng

        ev = entry.get("event") or entry.get("level", "UNKNOWN")
        event_counts[ev] = event_counts.get(ev, 0) + 1

    return {
        "log_type":     log_type,
        "total":        total,
        "first_ts":     first_ts,
        "last_ts":      last_ts,
        "event_counts": event_counts,
    }

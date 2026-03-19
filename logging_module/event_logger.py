# logging_module/event_logger.py
"""
Structured logging cho toàn bộ hệ thống Smart Door.
Mọi module khác import từ đây — KHÔNG tạo logger riêng.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

# Dùng absolute import chuẩn (Giả định entry point chạy từ thư mục gốc)
from config.constants import LOG_MAX_BYTES, LOG_BACKUP_COUNT

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class EventType(str, Enum):
    # Motion & recognition
    MOTION_DETECTED     = "MOTION_DETECTED"
    FACE_SUCCESS        = "FACE_SUCCESS"
    FACE_FAILED         = "FACE_FAILED"
    FACE_ATTEMPT        = "FACE_ATTEMPT"

    # Door
    DOOR_OPENED         = "DOOR_OPENED"
    DOOR_OPENED_PWD     = "DOOR_OPENED_PASSWORD"

    # Password
    PASSWORD_FAILED     = "PASSWORD_FAILED"
    PASSWORD_SUCCESS    = "PASSWORD_SUCCESS"
    PIN_SYNCED          = "PIN_SYNCED"
    PIN_SYNC_FAILED     = "PIN_SYNC_FAILED"

    # Alarm
    ALARM_ACTIVE        = "ALARM_ACTIVE"
    ALARM_STOPPED       = "ALARM_STOPPED"

    # UART
    UART_SENT           = "UART_SENT"
    UART_RECEIVED       = "UART_RECEIVED"
    UART_ERROR          = "UART_ERROR"

    # Cloud
    CLOUD_UPLOAD_OK     = "CLOUD_UPLOAD_OK"
    CLOUD_UPLOAD_FAIL   = "CLOUD_UPLOAD_FAIL"

    # System
    SYSTEM_START        = "SYSTEM_START"
    SYSTEM_STOP         = "SYSTEM_STOP"
    SYSTEM_ERROR        = "SYSTEM_ERROR"
    API_ERROR           = "API_ERROR"
    CAMERA_ON           = "CAMERA_ON"
    CAMERA_OFF          = "CAMERA_OFF"


# ── Custom Formatters ──────────────────────────────────────────────────────
class JsonFileFormatter(logging.Formatter):
    """Format dict thành JSON trên một dòng để ghi ra file (Machine-readable)."""
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            return json.dumps(record.msg, ensure_ascii=False, default=str)
        return str(record.getMessage())


class ConsoleFormatter(logging.Formatter):
    """Format dict thành chuỗi dễ đọc cho human khi debug trên console Terminal."""
    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            msg_text = record.msg.get("msg") or record.msg.get("event") or ""
            # Lọc các metadata nội bộ, chỉ in các tham số extra ở cuối dòng
            extras = {k: v for k, v in record.msg.items() if k not in ("ts", "level", "msg", "event")}
            extra_str = f" | {extras}" if extras else ""
            return f"[{self.formatTime(record, '%H:%M:%S')}] [{record.levelname}] {msg_text}{extra_str}"

        # Fallback an toàn nếu log theo kiểu string truyền thống
        return f"[{self.formatTime(record, '%H:%M:%S')}] [{record.levelname}] {record.getMessage()}"


# ── Internal logger factory ────────────────────────────────────────────────
def _build_logger(name: str, filename: str) -> logging.Logger:
    logger = logging.getLogger(f"smartdoor.{name}")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False # Tránh in đúp log lên root logger

    # File handler có rotation (Cắt file khi đầy, giữ lại file cũ)
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / filename,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(JsonFileFormatter())
    logger.addHandler(fh)

    # Console handler (In ra màn hình Terminal)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(ConsoleFormatter())
    logger.addHandler(ch)

    return logger


_app_logger   = _build_logger("app",    "app.log")
_event_logger = _build_logger("events", "events.log")


def _now() -> str:
    """Hàm tiện ích lấy ISO timestamp chuẩn đến từng giây."""
    return datetime.now().isoformat(timespec="seconds")


# ── Public API ────────────────────────────────────────────────────────────
def log_app(level: Literal["debug", "info", "warning", "error", "critical"], message: str, **extra: Any) -> None:
    """Log sự kiện hệ thống vào app.log."""
    entry = {"ts": _now(), "level": level.upper(), "msg": message, **extra}
    fn = getattr(_app_logger, level.lower(), _app_logger.info)
    fn(entry)  # Truyền trực tiếp dict vào logger


def log_event(event_type: EventType, **data: Any) -> None:
    """Log sự kiện an ninh vào events.log."""
    entry = {"ts": _now(), "event": event_type.value, **data}
    _event_logger.info(entry)

    # Escalate: Báo động kép các sự kiện quan trọng sang app.log để Dev dễ monitor
    if event_type in {
        EventType.ALARM_ACTIVE,
        EventType.SYSTEM_ERROR,
        EventType.UART_ERROR,
        EventType.CLOUD_UPLOAD_FAIL,
    }:
        log_app("warning", f"Security/System Alert: {event_type.value}", **data)


def log_uart(direction: Literal["TX", "RX"], frame: str) -> None:
    """Shortcut để log UART traffic."""
    etype = EventType.UART_SENT if direction == "TX" else EventType.UART_RECEIVED
    log_event(etype, direction=direction, frame=frame.strip())


def log_access(name: str | None, method: Literal["face", "password"], success: bool, image_url: str = "") -> None:
    """Shortcut để log kết quả mở cửa (Gắn với ảnh và danh tính)."""
    if method == "face":
        etype = EventType.FACE_SUCCESS if success else EventType.FACE_FAILED
    else:
        etype = EventType.DOOR_OPENED_PWD if success else EventType.PASSWORD_FAILED

    log_event(
        etype,
        name=name or "unknown",
        method=method,
        success=success,
        image_url=image_url,
    )


def get_log_paths() -> dict[str, Path]:
    """Trả về đường dẫn tuyệt đối của các file log (Dùng cho log server nếu có)."""
    return {
        "app":    LOG_DIR / "app.log",
        "events": LOG_DIR / "events.log",
    }

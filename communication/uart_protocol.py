# communication/uart_protocol.py
"""
Định nghĩa toàn bộ UART protocol giữa Raspberry Pi và STM32.
File này KHÔNG có I/O — chỉ chứa constants và helper functions.
Mọi module khác import từ đây để tránh hardcode string.
"""
from __future__ import annotations
from config.constants import (
    CMD_UNLOCK_DOOR, CMD_ENABLE_KEYPAD, CMD_STOP_ALARM, CMD_SET_PIN,
    EVT_MOTION_DETECTED,
    RSP_DOOR_OPENED, RSP_DOOR_OPENED_PWD,
    RSP_PASSWORD_FAILED, RSP_ALARM_ACTIVE, RSP_ACK_PIN_SET,
)

# ── Frame format ──────────────────────────────────────────────────────────
# Mỗi frame là một dòng text kết thúc bằng \n
# CRC8 đơn giản append vào cuối: "CMD_UNLOCK_DOOR:A3\n"

def _crc8(data: str) -> str:
    """
    Tính toán mã kiểm tra CRC-8 (Polynomial 0x07).
    Đủ nhẹ để STM32 tính toán đồng bộ trong firmware C.
    """
    crc = 0
    # Ép kiểu utf-8 an toàn để đảm bảo mọi ký tự đều được băm chính xác
    for b in data.encode('utf-8'):
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return f"{crc:02X}"


def build_frame(cmd: str) -> str:
    """Đóng gói lệnh thành frame chuẩn có mã CRC: 'CMD:CRC\n'"""
    checksum = _crc8(cmd)
    return f"{cmd}:{checksum}\n"


def parse_frame(raw: str) -> tuple[str, bool]:
    """
    Tách payload và kiểm tra độ vẹn toàn CRC.
    Trả về (payload, crc_ok).
    Nếu frame không có dấu ':' → coi là Legacy Mode (không có CRC), valid=True.
    """
    raw = raw.strip()

    # Firmware cũ chưa code CRC, hoặc lệnh đặc biệt không cần CRC
    if ":" not in raw:
        return raw, True

    # rsplit(":", 1) đảm bảo tách đúng ở dấu hai chấm cuối cùng (an toàn)
    payload, checksum = raw.rsplit(":", 1)
    expected = _crc8(payload)

    # So sánh không phân biệt hoa/thường để tránh lỗi do code C xuất ra "a3" thay vì "A3"
    is_valid = (checksum.upper() == expected.upper())
    return payload, is_valid


# ── Command builders ──────────────────────────────────────────────────────
def frame_unlock_door() -> str:
    return build_frame(CMD_UNLOCK_DOOR)

def frame_enable_keypad() -> str:
    return build_frame(CMD_ENABLE_KEYPAD)

def frame_stop_alarm() -> str:
    return build_frame(CMD_STOP_ALARM)

def frame_set_pin(hmac_hex: str) -> str:
    # Không cần encode colon vì rsplit() phía nhận xử lý an toàn
    return build_frame(f"{CMD_SET_PIN} {hmac_hex}")


# ── Response classifier ───────────────────────────────────────────────────
# Map trực tiếp chuỗi lệnh vật lý thành Event Key chuẩn để Router xử lý
RESPONSE_MAP: dict[str, str] = {
    EVT_MOTION_DETECTED:  "motion",
    RSP_DOOR_OPENED:      "door_opened",
    RSP_DOOR_OPENED_PWD:  "door_opened_pwd",
    RSP_PASSWORD_FAILED:  "password_failed",
    RSP_ALARM_ACTIVE:     "alarm_active",
    RSP_ACK_PIN_SET:      "ack_pin_set",
}

def classify_response(payload: str) -> str | None:
    """Trả về key handler (đã chuẩn hóa) hoặc None nếu đó là gói tin lạ."""
    return RESPONSE_MAP.get(payload.strip())

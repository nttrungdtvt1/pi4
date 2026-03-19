# tests/test_uart_protocol.py
"""
Tests cho module uart_protocol.
Kiểm tra tính đúng đắn của việc đóng gói/mở gói (pack/unpack) frame UART,
thuật toán CRC8 và logic phân loại (classify).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from communication.uart_protocol import (
    _crc8, build_frame, parse_frame, classify_response,
    frame_unlock_door, frame_set_pin
)
from config.constants import (
    CMD_UNLOCK_DOOR, CMD_SET_PIN,
    EVT_MOTION_DETECTED, RSP_PASSWORD_FAILED
)

class TestUartProtocol:
    def test_crc8_consistency(self):
        """Kiểm tra CRC8 sinh ra phải cố định với cùng một chuỗi đầu vào."""
        payload = "TEST_PAYLOAD"
        crc1 = _crc8(payload)
        crc2 = _crc8(payload)
        assert crc1 == crc2
        assert isinstance(crc1, str)
        assert len(crc1) == 2  # Mã hex 2 ký tự (VD: "A3")

    def test_build_frame(self):
        """Frame phải có định dạng PAYLOAD:CRC\\n"""
        cmd = "HELLO"
        crc = _crc8(cmd)
        frame = build_frame(cmd)
        assert frame == f"{cmd}:{crc}\n"

    def test_parse_frame_valid(self):
        """Parse frame đúng chuẩn phải trả về payload và crc_ok = True."""
        cmd = "OPEN_DOOR"
        frame = build_frame(cmd)
        payload, crc_ok = parse_frame(frame)
        assert payload == cmd
        assert crc_ok is True

    def test_parse_frame_invalid_crc(self):
        """Parse frame bị sai lệch dữ liệu trên đường truyền (nhiễu UART)."""
        # Giả lập nhiễu làm đổi 1 ký tự nhưng giữ nguyên CRC cũ
        corrupted_frame = "OPEN_DOOR_X:A3\n"
        payload, crc_ok = parse_frame(corrupted_frame)
        assert payload == "OPEN_DOOR_X"
        assert crc_ok is False

    def test_parse_frame_legacy(self):
        """Parse frame từ firmware cũ (không có dấu ':' và CRC)."""
        legacy_frame = "DOOR_OPENED\n"
        payload, crc_ok = parse_frame(legacy_frame)
        assert payload == "DOOR_OPENED"
        assert crc_ok is True  # Mặc định chấp nhận

    def test_command_builders(self):
        """Kiểm tra các hàm tạo frame cụ thể có bọc đúng lệnh hằng số không."""
        frame = frame_unlock_door()
        assert frame.startswith(CMD_UNLOCK_DOOR)
        assert frame.endswith("\n")

        pin_frame = frame_set_pin("DEADBEEF")
        assert pin_frame.startswith(f"{CMD_SET_PIN} DEADBEEF")

    def test_classify_response(self):
        """Kiểm tra bộ phân loại nhận diện đúng sự kiện hệ thống."""
        assert classify_response(EVT_MOTION_DETECTED) == "motion"
        assert classify_response(RSP_PASSWORD_FAILED) == "password_failed"
        assert classify_response("UNKNOWN_GARBAGE") is None

# communication/uart_handler.py
"""
Quản lý kết nối UART vật lý với STM32.
- Lắng nghe liên tục bằng MỘT luồng đọc duy nhất.
- Gửi lệnh có retry + ACK timeout sử dụng asyncio.Event để đồng bộ.
"""
from __future__ import annotations

import asyncio
import serial

from config.settings import settings
from config.constants import UART_SEND_RETRY, UART_ACK_TIMEOUT
from communication.uart_protocol import parse_frame
from logging_module.event_logger import log_uart, log_app, EventType, log_event


class UartHandler:
    def __init__(self):
        self._ser: serial.Serial | None = None
        self._connected = False
        self._send_lock = asyncio.Lock()

        # Cơ chế đồng bộ ACK
        self._expected_ack: str | None = None
        self._ack_event = asyncio.Event()

    def connect(self) -> None:
        try:
            self._ser = serial.Serial(
                port=settings.uart_port,
                baudrate=settings.uart_baud,
                timeout=1.0,
                write_timeout=2.0,
            )
            self._connected = True
            log_app("info", "UART connected",
                    port=settings.uart_port, baud=settings.uart_baud)
        except serial.SerialException as exc:
            log_event(EventType.UART_ERROR, detail=str(exc), phase="connect")
            raise

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
            self._connected = False
            log_app("info", "UART closed")

    async def listen_loop(self, queue: asyncio.Queue[str]) -> None:
        """Luồng DUY NHẤT đọc dữ liệu từ UART."""
        log_app("info", "UART listen loop started")
        loop = asyncio.get_running_loop()

        while True:
            try:
                # Tránh treo Event Loop, đưa tác vụ đọc I/O chặn xuống ThreadPool
                raw: bytes = await loop.run_in_executor(None, self._ser.readline)
                if not raw:
                    continue

                decoded = raw.decode("utf-8", errors="replace").strip()
                if not decoded:
                    continue

                payload, crc_ok = parse_frame(decoded)
                log_uart("RX", decoded)

                if not crc_ok:
                    log_event(EventType.UART_ERROR, detail="CRC mismatch", raw=decoded)
                    continue

                # Nếu là ACK mà tiến trình send() đang chờ -> Kích hoạt Event
                if self._expected_ack and payload == self._expected_ack:
                    self._ack_event.set()
                else:
                    # Các event khác (như motion, button) đẩy vào queue cho event_handler
                    await queue.put(payload)

            except serial.SerialException as exc:
                log_event(EventType.UART_ERROR, detail=str(exc), phase="read")
                await asyncio.sleep(2)  # Đợi một chút trước khi thử đọc lại để tránh spam CPU
            except asyncio.CancelledError:
                log_app("info", "UART listen loop cancelled")
                raise
            except Exception as exc:
                log_event(EventType.UART_ERROR, detail=f"Unexpected: {exc}", phase="read")
                await asyncio.sleep(1)

    async def send(self, frame: str, expect_ack: str | None = None) -> bool:
        """Gửi lệnh và đợi báo hiệu từ listen_loop nếu cần ACK."""
        async with self._send_lock:
            self._expected_ack = expect_ack

            for attempt in range(1, UART_SEND_RETRY + 1):
                # LUÔN XÓA CỜ EVENT TRƯỚC KHI GỬI (Fix lỗi Late ACK từ lần thử trước)
                self._ack_event.clear()

                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None, lambda: self._ser.write(frame.encode("utf-8"))
                    )
                    log_uart("TX", frame.strip())

                    if not expect_ack:
                        self._expected_ack = None
                        return True

                    # Chờ listen_loop báo hiệu nhận được ACK
                    try:
                        await asyncio.wait_for(self._ack_event.wait(), timeout=UART_ACK_TIMEOUT)
                        self._expected_ack = None  # Reset state thành công
                        return True
                    except asyncio.TimeoutError:
                        log_app("warning", f"No ACK (attempt {attempt}/{UART_SEND_RETRY})",
                                expected=expect_ack, frame=frame.strip())

                        # Nghỉ một nhịp siêu ngắn trước khi nhồi lại dữ liệu để STM32 kịp thở
                        if attempt < UART_SEND_RETRY:
                            await asyncio.sleep(0.1)

                except serial.SerialException as exc:
                    log_event(EventType.UART_ERROR, detail=str(exc), phase="write", attempt=attempt)
                    await asyncio.sleep(0.5)

            # Xóa expected_ack nếu tất cả các lần thử đều thất bại
            self._expected_ack = None
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected and bool(self._ser) and self._ser.is_open

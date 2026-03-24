#!/usr/bin/env python3
"""
pi4/tests/test_force_face_scan.py

MỤC ĐÍCH:
    Bỏ qua bước chờ tín hiệu chuyển động từ cảm biến PIR.
    Kích hoạt trực tiếp module Camera và PresenceDetector để vào chế độ
    quét khuôn mặt ngay lập tức.

    ✅ SAU KHI SỬA: In rõ THÀNH CÔNG / THẤT BẠI sau mỗi lần quét,
    kèm thống kê tổng cuối cùng để dễ debug.
"""

import sys
import asyncio
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# -- Đường dẫn project --
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# UART helpers
# ---------------------------------------------------------------------------

def _crc8(data: str) -> str:
    crc = 0
    for b in data.encode("utf-8"):
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return f"{crc:02X}"


def build_frame(cmd: str) -> str:
    return f"{cmd}:{_crc8(cmd)}\n"


CMD_FACE_SCAN_START = "CMD_WARNING_BEEP"
CMD_LOCK_DOOR       = "CMD_LOCK_DOOR"


# ---------------------------------------------------------------------------
# Bộ đếm kết quả — lưu toàn bộ lịch sử mỗi lần quét
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    attempt: int
    success: bool
    name: Optional[str] = None
    distance: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    reason: str = ""   # mô tả ngắn lý do thất bại nếu có


class TestStats:
    """Ghi lại kết quả từng lần quét, in báo cáo cuối."""

    def __init__(self):
        self.results: list[ScanResult] = []
        self._attempt = 0
        self.final_outcome: Optional[bool] = None   # True=pass, False=fail

    def record_success(self, name: str, distance: float):
        self._attempt += 1
        r = ScanResult(
            attempt=self._attempt,
            success=True,
            name=name,
            distance=distance,
        )
        self.results.append(r)
        print(f"\n{'='*55}")
        print(f"  ✅  THÀNH CÔNG — Nhận diện được khuôn mặt!")
        print(f"      Tên       : {name}")
        print(f"      Distance  : {distance:.4f}  (càng nhỏ càng giống)")
        print(f"      Lần quét  : #{self._attempt}  lúc {r.timestamp}")
        print(f"{'='*55}\n")
        self.final_outcome = True

    def record_failure(self, distance: float, reason: str = "Không nhận ra khuôn mặt"):
        self._attempt += 1
        r = ScanResult(
            attempt=self._attempt,
            success=False,
            distance=distance,
            reason=reason,
        )
        self.results.append(r)
        print(f"\n{'─'*55}")
        print(f"  ❌  THẤT BẠI — Lần #{self._attempt}  lúc {r.timestamp}")
        print(f"      Lý do     : {reason}")
        print(f"      Distance  : {distance:.4f}  (ngưỡng thường là 0.45-0.6)")
        print(f"{'─'*55}\n")

    def record_alarm(self):
        self._attempt += 1
        r = ScanResult(
            attempt=self._attempt,
            success=False,
            reason="QUÁ SỐ LẦN THẤT BẠI → ALARM",
        )
        self.results.append(r)
        print(f"\n{'!'*55}")
        print(f"  🚨  ALARM — Đã quét {self._attempt} lần, không nhận ra ai.")
        print(f"{'!'*55}\n")
        self.final_outcome = False

    def print_summary(self):
        total  = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed

        print("\n" + "=" * 55)
        print("  📊  KẾT QUẢ TỔNG KẾT")
        print("=" * 55)
        print(f"  Tổng số lần quét : {total}")
        print(f"  ✅ Thành công    : {passed}")
        print(f"  ❌ Thất bại      : {failed}")

        if self.results:
            print("\n  Chi tiết từng lần:")
            for r in self.results:
                icon = "✅" if r.success else "❌"
                dist_str = f"dist={r.distance:.4f}" if r.distance is not None else ""
                name_str = f"→ {r.name}" if r.name else ""
                reason_str = f"[{r.reason}]" if r.reason and not r.success else ""
                print(f"    #{r.attempt:02d} {icon}  {r.timestamp}  "
                      f"{dist_str}  {name_str} {reason_str}")

        print()
        if self.final_outcome is True:
            print("  🎉  CAMERA & MÔ HÌNH HOẠT ĐỘNG ĐÚNG — Nhận diện thành công!")
        elif self.final_outcome is False:
            print("  ⚠️   NHẬN DIỆN THẤT BẠI — Kiểm tra các điểm sau:")
            print("      1. Khuôn mặt đã được enroll chưa? (chạy enroll_face.py)")
            print("      2. Ánh sáng có đủ không? (tránh ngược sáng)")
            print("      3. Khoảng cách camera: 30-60 cm là tốt nhất")
            print("      4. Distance quá cao → thêm ảnh training đa góc độ")
            print("      5. Kiểm tra known_faces.pkl có được cập nhật chưa")
        else:
            print("  ℹ️   Chưa có kết quả (detector không hoàn thành chu kỳ).")
            print("      Thử tăng timeout hoặc kiểm tra camera.")

        print("=" * 55 + "\n")


# ---------------------------------------------------------------------------
# Mock classes
# ---------------------------------------------------------------------------

class MockUartHandler:
    is_connected = True

    async def send(self, frame: str, expect_ack=None) -> bool:
        print(f"  [MOCK UART TX] → {frame.strip()}")
        return True

    def connect(self):
        print("  [MOCK UART] Connected (dry-run mode)")

    async def listen_loop(self, *args, **kwargs):
        await asyncio.sleep(9999)


class MockCameraManager:
    is_active = True

    async def camera_on(self):
        print("  [MOCK CAM] Camera ON (frame đen — dry-run)")

    async def camera_off(self):
        print("  [MOCK CAM] Camera OFF")

    async def capture_frame(self):
        import numpy as np
        return np.zeros((480, 640, 3), dtype=np.uint8)

    async def __aenter__(self):
        await self.camera_on()
        return self

    async def __aexit__(self, *args):
        await self.camera_off()


# ---------------------------------------------------------------------------
# UART helpers
# ---------------------------------------------------------------------------

async def send_lcd_scanning_state(uart) -> None:
    print("\n[UART] Gửi lệnh xuống STM32...")
    frame_lock = build_frame(CMD_LOCK_DOOR)
    ok = await uart.send(frame_lock)
    print(f"  → CMD_LOCK_DOOR: {'OK ✅' if ok else 'FAIL ❌'}")
    await asyncio.sleep(0.2)

    frame_scan = build_frame(CMD_FACE_SCAN_START)
    ok = await uart.send(frame_scan)
    print(f"  → CMD_WARNING_BEEP: {'OK ✅' if ok else 'FAIL ❌'}")
    await asyncio.sleep(0.3)
    print("[UART] STM32 đã nhận lệnh\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(dry_run: bool) -> None:
    print("=" * 55)
    print("  TEST: test_force_face_scan.py")
    print("  Bỏ qua PIR → quét khuôn mặt ngay lập tức")
    if dry_run:
        print("  CHẾ ĐỘ: DRY-RUN (mock hardware)")
    print("=" * 55)

    stats = TestStats()

    async def on_recognized_cb(result):
        stats.record_success(name=result.name, distance=result.distance)

    async def on_unknown_cb(result):
        stats.record_failure(
            distance=result.distance,
            reason="Khuôn mặt không khớp với bất kỳ người nào trong CSDL"
        )

    async def on_alarm_cb():
        stats.record_alarm()

    async def broadcast_cb(event_type: str, data: dict):
        if event_type not in ("scan_frame",):
            print(f"  [WS] {event_type}: {data}")

    # -- Khởi tạo hardware / mock --
    if dry_run:
        uart   = MockUartHandler()
        uart.connect()
        camera = MockCameraManager()
    else:
        from communication.uart_handler import UartHandler
        from vision.camera_manager import CameraManager
        from config.settings import settings

        uart = UartHandler()
        try:
            uart.connect()
            print(f"[UART] Kết nối tới {settings.uart_port} @ {settings.uart_baud}bps ✅")
        except Exception as exc:
            print(f"[UART] ❌ Kết nối thất bại: {exc}")
            return

        camera = CameraManager()

    await send_lcd_scanning_state(uart)

    print("[CAMERA] Khởi động camera...")
    await camera.camera_on()
    if not dry_run:
        print("[CAMERA] ✅ Sẵn sàng")

    print("[DETECTOR] Khởi tạo PresenceDetector...")
    try:
        import control.presence_detector as pd_module

        # ⚡ KỸ THUẬT MONKEY PATCHING: Nới lỏng cấu hình an ninh TẠM THỜI chỉ trong lúc test
        pd_module.MIN_FACE_AREA = 3000
        pd_module.MAX_FACE_MOVEMENT = 150

        detector = pd_module.PresenceDetector(
            camera=camera,
            on_recognized=on_recognized_cb,
            on_unknown=on_unknown_cb,
            on_alarm=on_alarm_cb,
            broadcast_fn=broadcast_cb,
            uart_send_fn=uart.send,  # ⚡ THÊM UART ĐỂ TEST KÍCH HOẠT MÃ PIN
        )
        print("[DETECTOR] ✅ Sẵn sàng (Đã nới lỏng cấu hình Area & Movement)\n")
    except ImportError as exc:
        print(f"[DETECTOR] ❌ Import lỗi: {exc}")
        return

    print("─" * 55)
    print("  ⚡  Bắt đầu: IDLE → WATCH → STABILIZE → SCAN")
    print("  👤  Hãy đứng trước camera ngay bây giờ!")
    print("─" * 55 + "\n")

    tasks = []
    if not dry_run:
        listen_task = asyncio.create_task(
            uart.listen_loop(asyncio.Queue()),
            name="uart_listen_test",
        )
        tasks.append(listen_task)

    await detector.on_pir_triggered()

    timeout_s = 60
    print(f"[TEST] Chờ detector hoàn thành (timeout={timeout_s}s)...")
    try:
        from control.presence_detector import State
        for tick in range(timeout_s * 10):
            await asyncio.sleep(0.1)
            if detector.state == State.IDLE and tick > 10:
                print("[TEST] Detector đã về IDLE ✅")
                break
        else:
            print(f"[TEST] ⏱  Timeout {timeout_s}s — detector chưa về IDLE")
            if stats.final_outcome is None:
                stats.final_outcome = False
    except asyncio.CancelledError:
        pass
    finally:
        for t in tasks:
            t.cancel()

    await camera.camera_off()
    stats.print_summary()


def main():
    parser = argparse.ArgumentParser(
        description="Test: Bỏ qua PIR, kích hoạt quét khuôn mặt ngay lập tức"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chạy với mock hardware (không cần Pi/STM32 thật)"
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(dry_run=args.dry_run))
    except KeyboardInterrupt:
        print("\n\n[INFO] Dừng bởi Ctrl+C")


if __name__ == "__main__":
    main()

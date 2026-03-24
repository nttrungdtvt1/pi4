#!/usr/bin/env python3
"""
pi4/tests/test_force_pin_mode.py

MỤC ĐÍCH:
    Bỏ qua bước phải quét mặt sai 5 lần.
    Ép hệ thống chuyển ngay sang chế độ nhập mã PIN.

HÀNH ĐỘNG:
    1. Gửi lệnh UART CMD_ENABLE_KEYPAD xuống STM32 → STM32 bật Keypad
       và LCD hiển thị "NHAP MA PIN:" chờ người dùng thao tác.
    2. (Tùy chọn) Gửi cảnh báo "Nghi ngờ kẻ đột nhập" lên Web Dashboard
       qua API Backend để simulate đúng luồng bảo mật.
    3. In hướng dẫn nhập PIN cho người dùng.

CÁCH CHẠY (từ thư mục gốc pi4/):
    python tests/test_force_pin_mode.py [--dry-run] [--no-alert]

    --dry-run  : Chạy không cần phần cứng UART (dùng mock).
    --no-alert : Không gửi cảnh báo lên Web Dashboard.

SAU KHI CHẠY:
    - STM32 LCD sẽ hiển thị: "NHAP MA PIN:"
    - Người dùng nhập PIN trên keypad vật lý
    - Nhập đúng: STM32 mở cửa + gửi EVENT_DOOR_OPENED_PWD → Pi log lại
    - Nhập sai 3 lần: STM32 kích hoạt Alarm + gửi ALARM_ACTIVE → Pi xử lý 180s
"""

import sys
import asyncio
import argparse
from datetime import datetime
from pathlib import Path

# -- Đường dẫn project --
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# UART helpers (CRC frame — phải khớp 100% với uart_protocol.py)
# ---------------------------------------------------------------------------

def _crc8(data: str) -> str:
    """CRC-8 (Poly 0x07) — nhất quán với production code."""
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
    """Đóng gói lệnh thành frame chuẩn: 'CMD:CRC\\n'"""
    return f"{cmd}:{_crc8(cmd)}\n"


# Constants — phải khớp với config/constants.py
CMD_ENABLE_KEYPAD  = "CMD_ENABLE_KEYPAD"
CMD_WARNING_BEEP   = "CMD_WARNING_BEEP"
CMD_LOCK_DOOR      = "CMD_LOCK_DOOR"
CMD_STOP_ALARM     = "CMD_STOP_ALARM"

# Event type gửi lên Backend
EVENT_INTRUDER_SUSPECTED = "face_unknown"


# ---------------------------------------------------------------------------
# Mock classes (dùng khi --dry-run)
# ---------------------------------------------------------------------------

class MockUartHandler:
    """Giả lập UartHandler khi không có phần cứng."""
    is_connected = True

    async def send(self, frame: str, expect_ack=None) -> bool:
        print(f"  [MOCK UART TX] → {frame.strip()}")
        return True

    def connect(self):
        print("  [MOCK UART] Connected (dry-run mode)")

    async def listen_loop(self, event_queue: asyncio.Queue, *args, **kwargs):
        """Giả lập STM32 gửi EVENT_PWD_FAILED sau 3 giây (để test alarm flow)."""
        await asyncio.sleep(3)
        print("\n  [MOCK STM32] Giả lập người dùng nhập sai PIN...")
        for i in range(1, 4):
            await asyncio.sleep(1.5)
            print(f"  [MOCK STM32] Gửi EVENT_PWD_FAILED (lần {i}/3)")
            await event_queue.put("EVENT_PWD_FAILED")
        # Sau 3 lần sai, STM32 sẽ gửi ALARM_ACTIVE
        await asyncio.sleep(0.5)
        print("  [MOCK STM32] Gửi ALARM_ACTIVE (nhập sai 3 lần!)")
        await event_queue.put("ALARM_ACTIVE")


# ---------------------------------------------------------------------------
# Hàm gửi cảnh báo lên Web Dashboard
# ---------------------------------------------------------------------------

async def notify_web_dashboard(api_url: str, api_key: str, send_alert: bool) -> None:
    """
    Gửi sự kiện "Nghi ngờ kẻ đột nhập" lên Backend.
    Đây là bước bắt buộc TRƯỚC khi chuyển sang PIN mode theo yêu cầu bảo mật.
    """
    if not send_alert:
        print("[WEB] --no-alert: Bỏ qua bước gửi cảnh báo lên Dashboard")
        return

    print("\n[WEB] Gửi cảnh báo 'Nghi ngờ kẻ đột nhập' lên Web Dashboard...")

    try:
        import aiohttp
        payload = {
            "type": EVENT_INTRUDER_SUSPECTED,
            "payload": {
                "reason": "intruder_suspected",
                "failed_attempts": 5,   # Giả lập đã thất bại 5 lần
                "test_mode": True,
                "triggered_by": "test_force_pin_mode.py",
            },
            "timestamp": datetime.now().isoformat(),
        }
        headers = {
            "X-Pi-Api-Key": api_key,
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{api_url}/api/events/",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5.0),
            ) as resp:
                if resp.status in (200, 201):
                    print(f"[WEB] ✅ Cảnh báo đã gửi thành công (HTTP {resp.status})")
                    print("[WEB]    Dashboard sẽ hiển thị: 'Nghi ngờ kẻ đột nhập!'")
                else:
                    body = await resp.text()
                    print(f"[WEB] ⚠️  HTTP {resp.status}: {body[:100]}")
                    print("[WEB]    Tiếp tục chạy test (cảnh báo không bắt buộc)")

    except ImportError:
        print("[WEB] ❌ aiohttp không được cài. Bỏ qua bước gửi cảnh báo.")
    except Exception as exc:
        print(f"[WEB] ⚠️  Gửi cảnh báo thất bại: {exc}")
        print("[WEB]    Tiếp tục chạy test...")


# ---------------------------------------------------------------------------
# Hàm gửi chuỗi lệnh UART để chuyển STM32 sang PIN mode
# ---------------------------------------------------------------------------

async def send_pin_mode_commands(uart) -> bool:
    """
    Gửi đúng thứ tự lệnh xuống STM32 để kích hoạt chế độ nhập PIN.

    Luồng lệnh:
      1. CMD_LOCK_DOOR      → Đảm bảo cửa đang khóa
      2. CMD_WARNING_BEEP   → Báo hiệu nhận diện thất bại (còi 3 tiếng)
                               LCD: "CANH BAO! / NHAN DIEN SAI"
      3. CMD_ENABLE_KEYPAD  → Chính thức bật keypad
                               LCD: (State machine STM32 chờ nhập PIN)
    """
    print("\n[UART] Gửi chuỗi lệnh xuống STM32 để kích hoạt PIN mode...")

    # ── Bước 1: Đảm bảo cửa khóa ──
    frame = build_frame(CMD_LOCK_DOOR)
    ok = await uart.send(frame)
    print(f"  Bước 1/3 → CMD_LOCK_DOOR:  {'✅ OK' if ok else '❌ FAIL'}")
    await asyncio.sleep(0.2)

    # ── Bước 2: Cảnh báo nhận diện mặt thất bại ──
    frame = build_frame(CMD_WARNING_BEEP)
    ok = await uart.send(frame)
    print(f"  Bước 2/3 → CMD_WARNING_BEEP: {'✅ OK' if ok else '❌ FAIL'}")
    print("             STM32 LCD: 'CANH BAO! / NHAN DIEN SAI' + còi 3 tiếng")
    await asyncio.sleep(1.5)   # Chờ STM32 hoàn tất hiệu ứng còi

    # ── Bước 3: Bật keypad — LỆNH QUAN TRỌNG NHẤT ──
    frame = build_frame(CMD_ENABLE_KEYPAD)
    ok = await uart.send(frame)
    print(f"  Bước 3/3 → CMD_ENABLE_KEYPAD: {'✅ OK' if ok else '❌ FAIL'}")
    print("             STM32 LCD: 'NHAP MA PIN:' — Keypad đã sẵn sàng!")

    return ok


# ---------------------------------------------------------------------------
# Listener đơn giản để theo dõi phản hồi từ STM32
# ---------------------------------------------------------------------------

async def monitor_stm32_responses(uart, duration: int = 30) -> None:
    """
    Lắng nghe và in các sự kiện STM32 gửi lên trong khi người dùng nhập PIN.
    Dừng sau 'duration' giây hoặc khi nhận được kết quả cuối cùng.
    """
    print(f"\n[MONITOR] Lắng nghe phản hồi từ STM32 (timeout={duration}s)...")
    print("[MONITOR] Nhập PIN trên keypad STM32 ngay bây giờ...\n")

    uart_rx_queue: asyncio.Queue = asyncio.Queue()

    # Bắt đầu listen trong background
    async def _listen():
        try:
            await uart.listen_loop(uart_rx_queue)
        except asyncio.CancelledError:
            pass

    listen_task = asyncio.create_task(_listen(), name="pin_monitor_listen")

    # Theo dõi events
    pwd_fail_count = 0
    start_time = asyncio.get_event_loop().time()

    try:
        while asyncio.get_event_loop().time() - start_time < duration:
            try:
                raw_event = await asyncio.wait_for(
                    uart_rx_queue.get(),
                    timeout=1.0
                )
                elapsed = asyncio.get_event_loop().time() - start_time

                if "EVENT_DOOR_OPENED_PWD" in raw_event:
                    print(f"  [{elapsed:5.1f}s] ✅ CỬA MỞ! Nhập PIN đúng.")
                    print("              Kết thúc test thành công.")
                    break

                elif "EVENT_PWD_FAILED" in raw_event:
                    pwd_fail_count += 1
                    print(f"  [{elapsed:5.1f}s] ⚠️  Nhập sai PIN (lần {pwd_fail_count}/3)")
                    if pwd_fail_count >= 3:
                        print("              Đã sai 3 lần — chờ STM32 kích hoạt Alarm...")

                elif "ALARM_ACTIVE" in raw_event:
                    print(f"  [{elapsed:5.1f}s] 🚨 ALARM! STM32 đã kích hoạt còi báo động.")
                    print("              Pi sẽ bắt đầu đếm ngược 180 giây.")
                    print("              Để dừng sớm: gửi CMD_STOP_ALARM từ Dashboard.")
                    break

                else:
                    print(f"  [{elapsed:5.1f}s] 📨 STM32: {raw_event.strip()}")

            except asyncio.TimeoutError:
                remaining = int(duration - (asyncio.get_event_loop().time() - start_time))
                if remaining % 5 == 0 and remaining > 0:
                    print(f"  [WAIT] Đang chờ nhập PIN... còn {remaining}s")

    finally:
        listen_task.cancel()
        try:
            await listen_task
        except asyncio.CancelledError:
            pass

    print("\n[MONITOR] Kết thúc theo dõi.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run(dry_run: bool, send_alert: bool) -> None:
    print("=" * 60)
    print(" TEST: test_force_pin_mode.py")
    print(" MỤC ĐÍCH: Bỏ qua quét mặt, ép vào chế độ nhập PIN")
    if dry_run:
        print(" CHẾ ĐỘ: DRY-RUN (không cần phần cứng)")
    print("=" * 60)

    # -- Lấy config --
    try:
        from config.settings import settings
        api_url = settings.api_server_url
        api_key = settings.api_key
    except ImportError:
        # Fallback khi chạy ngoài môi trường pi4
        api_url = "http://192.168.137.1:8000"
        api_key = "raspberry-pi-secret-key"
        print(f"[CONFIG] Dùng giá trị mặc định: {api_url}")

    # -- Khởi tạo UART --
    if dry_run:
        uart = MockUartHandler()
        uart.connect()
    else:
        try:
            from communication.uart_handler import UartHandler
            uart = UartHandler()
            uart.connect()
            print(f"[UART] ✅ Kết nối UART thành công")
        except Exception as exc:
            print(f"[UART] ❌ Kết nối thất bại: {exc}")
            print("       Gợi ý: Dùng --dry-run để test không cần phần cứng")
            return

    # ═══════════════════════════════════════════════════════
    # LUỒNG BẢO MẬT CHÍNH:
    # Bước 1: Gửi cảnh báo lên Web TRƯỚC khi chuyển sang PIN
    # ═══════════════════════════════════════════════════════
    await notify_web_dashboard(api_url, api_key, send_alert)

    # ═══════════════════════════════════════════════════════
    # Bước 2: Gửi lệnh UART xuống STM32 → Kích hoạt PIN mode
    # ═══════════════════════════════════════════════════════
    success = await send_pin_mode_commands(uart)

    if not success:
        print("\n[TEST] ❌ Gửi lệnh UART thất bại. Kiểm tra kết nối.")
        return

    # ═══════════════════════════════════════════════════════
    # Bước 3: Hiển thị hướng dẫn cho người test
    # ═══════════════════════════════════════════════════════
    print("\n" + "─" * 60)
    print(" HƯỚNG DẪN NHẬP PIN (trên bàn phím STM32):")
    print("─" * 60)
    print("  📱 LCD hiện tại: 'NHAP MA PIN:'")
    print()
    print("  ➤ Nhập 6 chữ số PIN (mặc định: 1 2 3 4 5 6)")
    print("  ➤ Bấm # để xác nhận")
    print("  ➤ Bấm * để xóa và nhập lại")
    print()
    print("  Kết quả:")
    print("  ✅ Đúng PIN → STM32 mở cửa + gửi EVENT_DOOR_OPENED_PWD")
    print("  ❌ Sai 3 lần → STM32 kích hoạt Alarm 180s (còi hú liên tục)")
    print("─" * 60)

    # ═══════════════════════════════════════════════════════
    # Bước 4: Lắng nghe phản hồi từ STM32
    # ═══════════════════════════════════════════════════════
    if dry_run:
        print("\n[DRY-RUN] Giả lập người dùng nhập PIN trong 8 giây...")
        await monitor_stm32_responses(uart, duration=8)
    else:
        print()
        await monitor_stm32_responses(uart, duration=60)

    # ═══════════════════════════════════════════════════════
    # Bước 5: Dọn dẹp
    # ═══════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print(" TEST HOÀN THÀNH")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Test: Bỏ qua quét mặt, ép hệ thống vào chế độ nhập PIN"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chạy với mock hardware (không cần Pi/STM32 thật)"
    )
    parser.add_argument(
        "--no-alert",
        action="store_true",
        help="Không gửi cảnh báo lên Web Dashboard"
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(dry_run=args.dry_run, send_alert=not args.no_alert))
    except KeyboardInterrupt:
        print("\n\n[INFO] Dừng bởi người dùng (Ctrl+C)")


if __name__ == "__main__":
    main()

# # communication/pin_sync_service.py
# from __future__ import annotations

# import asyncio
# import hashlib
# import hmac

# from config.settings import settings
# from config.constants import RSP_ACK_PIN_SET, API_HEARTBEAT_INTERVAL
# from communication.uart_protocol import frame_set_pin
# from communication.api_client import get_pending_pin
# from logging_module.event_logger import log_app, log_event, EventType


# def _compute_hmac(pin: str) -> str:
#     """
#     Tạo mã băm bảo mật HMAC-SHA256 cho mã PIN.
#     Đảm bảo PIN thô không bao giờ bị truyền qua dây UART hay lưu trên log.
#     """
#     secret = settings.hmac_secret_key.encode('utf-8')
#     return hmac.new(secret, pin.encode('utf-8'), hashlib.sha256).hexdigest()


# class PinSyncService:
#     def __init__(self, uart_handler, pin_queue: asyncio.Queue[str]):
#         self._uart = uart_handler
#         self._queue = pin_queue

#     async def run(self) -> None:
#         """
#         Consumer: Lắng nghe hàng đợi, lấy PIN mới và đồng bộ xuống STM32.
#         """
#         log_app("info", "PinSyncService started")
#         while True:
#             try:
#                 new_pin: str = await self._queue.get()

#                 # Sử dụng try...finally để đảm bảo task_done() luôn được gọi
#                 try:
#                     await self._sync_pin(new_pin)
#                 except Exception as exc:
#                     log_event(EventType.SYSTEM_ERROR, detail=f"Error syncing PIN: {exc}")
#                 finally:
#                     self._queue.task_done()

#             except asyncio.CancelledError:
#                 log_app("info", "PinSyncService cancelled via system shutdown")
#                 raise
#             except Exception as exc:
#                 log_event(EventType.SYSTEM_ERROR, detail=f"PinSyncService.run fatal error: {exc}")

#     async def _sync_pin(self, pin: str) -> bool:
#         """
#         Xử lý mã hóa và gửi gói tin UART xuống STM32.
#         """
#         if not pin or len(pin) < 4:
#             log_app("warning", "PIN too short — rejected", length=len(pin))
#             return False

#         hmac_hex = _compute_hmac(pin)
#         frame = frame_set_pin(hmac_hex)

#         log_app("debug", f"Sending new PIN HMAC to STM32: {hmac_hex[:8]}...")

#         # Yêu cầu _uart.send phải hỗ trợ cơ chế chờ ACK (chờ STM32 phản hồi)
#         success = await self._uart.send(frame, expect_ack=RSP_ACK_PIN_SET)

#         if success:
#             log_event(EventType.PIN_SYNCED)
#             log_app("info", "PIN successfully synced to STM32")
#         else:
#             log_event(EventType.PIN_SYNC_FAILED, detail="No ACK from STM32 after retries")
#             log_app("error", "Failed to sync PIN to STM32")

#         return success


# async def poll_pin_changes(pin_queue: asyncio.Queue[str]) -> None:
#     """
#     Producer: Định kỳ hỏi Web Server xem Admin có yêu cầu đổi PIN không.
#     """
#     log_app("info", "PIN polling loop started")
#     while True:
#         try:
#             new_pin = await get_pending_pin()
#             if new_pin:
#                 log_app("info", "New PIN received from server — queuing sync")
#                 await pin_queue.put(new_pin)

#         except asyncio.CancelledError:
#             log_app("info", "PIN polling loop cancelled")
#             raise
#         except Exception as exc:
#             log_event(EventType.API_ERROR, detail=str(exc), phase="poll_pin_changes")

#         # Nghỉ theo chu kỳ nhịp tim để không spam Web Server
#         await asyncio.sleep(API_HEARTBEAT_INTERVAL)



# communication/pin_sync_service.py
from __future__ import annotations

import asyncio
import hashlib
import hmac

from config.settings import settings
from config.constants import RSP_ACK_PIN_SET, API_HEARTBEAT_INTERVAL
from communication.uart_protocol import frame_set_pin
from communication.api_client import get_pending_pin, ack_pin_sync
from logging_module.event_logger import log_app, log_event, EventType


def _compute_hmac(pin: str) -> str:
    """
    Tạo mã băm bảo mật HMAC-SHA256 cho mã PIN.
    Đảm bảo PIN thô không bao giờ bị truyền qua dây UART hay lưu trên log.
    """
    secret = settings.hmac_secret_key.encode('utf-8')
    return hmac.new(secret, pin.encode('utf-8'), hashlib.sha256).hexdigest()


class PinSyncService:
    def __init__(self, uart_handler, pin_queue: asyncio.Queue[str]):
        self._uart = uart_handler
        self._queue = pin_queue

    async def run(self) -> None:
        """
        Consumer: Lắng nghe hàng đợi, lấy PIN mới và đồng bộ xuống STM32.
        """
        log_app("info", "PinSyncService started")
        while True:
            try:
                new_pin: str = await self._queue.get()

                # Sử dụng try...finally để đảm bảo task_done() luôn được gọi
                try:
                    await self._sync_pin(new_pin)
                except Exception as exc:
                    log_event(EventType.SYSTEM_ERROR, detail=f"Error syncing PIN: {exc}")
                finally:
                    self._queue.task_done()

            except asyncio.CancelledError:
                log_app("info", "PinSyncService cancelled via system shutdown")
                raise
            except Exception as exc:
                log_event(EventType.SYSTEM_ERROR, detail=f"PinSyncService.run fatal error: {exc}")

    async def _sync_pin(self, pin: str) -> bool:
        """
        Xử lý mã hóa và gửi gói tin UART xuống STM32.
        Sau khi thành công, báo cáo Backend để xóa pin_plaintext.
        """
        if not pin or len(pin) < 4:
            log_app("warning", "PIN too short — rejected", length=len(pin))
            return False

        hmac_hex = _compute_hmac(pin)
        frame = frame_set_pin(hmac_hex)

        log_app("debug", f"Sending new PIN HMAC to STM32: {hmac_hex[:8]}...")

        # Yêu cầu _uart.send phải hỗ trợ cơ chế chờ ACK (chờ STM32 phản hồi)
        success = await self._uart.send(frame, expect_ack=RSP_ACK_PIN_SET)

        if success:
            log_event(EventType.PIN_SYNCED)
            log_app("info", "PIN successfully synced to STM32")
            # Báo cáo Backend để xóa pin_plaintext và đánh dấu pi_synced = True
            await ack_pin_sync()
        else:
            log_event(EventType.PIN_SYNC_FAILED, detail="No ACK from STM32 after retries")
            log_app("error", "Failed to sync PIN to STM32")

        return success


async def poll_pin_changes(pin_queue: asyncio.Queue[str]) -> None:
    """
    Producer: Định kỳ hỏi Web Server xem Admin có yêu cầu đổi PIN không.
    """
    log_app("info", "PIN polling loop started")
    while True:
        try:
            new_pin = await get_pending_pin()
            if new_pin:
                log_app("info", "New PIN received from server — queuing sync")
                await pin_queue.put(new_pin)

        except asyncio.CancelledError:
            log_app("info", "PIN polling loop cancelled")
            raise
        except Exception as exc:
            log_event(EventType.API_ERROR, detail=str(exc), phase="poll_pin_changes")

        # Nghỉ theo chu kỳ nhịp tim để không spam Web Server
        await asyncio.sleep(API_HEARTBEAT_INTERVAL)

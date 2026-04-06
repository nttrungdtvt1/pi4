# # # # control/door_controller.py
# # # from __future__ import annotations

# # # import asyncio
# # # from typing import Optional
# # # from pathlib import Path

# # # from config.settings import settings
# # # from config.constants import CMD_UNLOCK_DOOR, CMD_ENABLE_KEYPAD
# # # from vision.camera_manager import CameraManager
# # # from recognition.face_detector import detect_with_retry, RecognitionResult
# # # from communication.uart_protocol import frame_unlock_door, frame_enable_keypad
# # # from communication.cloud_uploader import upload
# # # from communication.api_client import post_access_log
# # # from logging_module.event_logger import log_app, log_access, EventType


# # # class DoorController:
# # #     def __init__(self, uart_handler):
# # #         self._uart   = uart_handler
# # #         self._camera = CameraManager()

# # #     async def run_recognition_cycle(self) -> RecognitionResult:
# # #         log_app("info", "Recognition cycle started")
# # #         result: Optional[RecognitionResult] = None

# # #         # Quản lý vòng đời camera tự động (bật lên và tự động tắt khi xong)
# # #         async with self._camera as cam:
# # #             result = await detect_with_retry(
# # #                 cam,
# # #                 max_attempts=settings.max_face_retry,
# # #                 tolerance=settings.face_tolerance,
# # #             )

# # #         # Fallback an toàn nếu nhận diện hoàn toàn thất bại hoặc lỗi camera
# # #         if result is None:
# # #             result = RecognitionResult(
# # #                 success=False,
# # #                 attempts=settings.max_face_retry,
# # #                 name="unknown",
# # #                 image_path=""
# # #             )

# # #         # ── Điều khiển STM32 NGAY LẬP TỨC để giảm độ trễ ──
# # #         if result.success:
# # #             await self._uart.send(frame_unlock_door())
# # #             log_app("info", "CMD_UNLOCK_DOOR sent", name=result.name)
# # #         else:
# # #             await self._uart.send(frame_enable_keypad())
# # #             log_app("info", "CMD_ENABLE_KEYPAD sent — switching to password mode")

# # #         # ── Xử lý I/O mạng ngầm (Background Tasks) ──
# # #         # Lưu reference của task và thêm callback để bắt lỗi nếu upload thất bại
# # #         bg_task = asyncio.create_task(self._background_logging_and_upload(result))
# # #         bg_task.add_done_callback(self._handle_bg_task_error)

# # #         return result

# # #     def _handle_bg_task_error(self, task: asyncio.Task) -> None:
# # #         """Bắt và ghi log nếu tác vụ chạy ngầm bị crash (vd: lỗi mạng nghiêm trọng)."""
# # #         try:
# # #             exc = task.exception()
# # #             if exc:
# # #                 log_app("error", f"Background upload/log task failed: {exc}")
# # #         except asyncio.CancelledError:
# # #             pass

# # #     async def _background_logging_and_upload(self, result: RecognitionResult) -> None:
# # #         """Upload ảnh và gọi API không làm block luồng mở cửa."""
# # #         image_url = ""

# # #         # Chỉ upload nếu có ảnh được chụp lại
# # #         if result.image_path:
# # #             url = await upload(Path(result.image_path))
# # #             image_url = url or ""

# # #         # Ghi log cục bộ lên thẻ nhớ
# # #         log_access(
# # #             name=result.name,
# # #             method="face",
# # #             success=result.success,
# # #             image_url=image_url,
# # #         )

# # #         # Đẩy sự kiện lên Web Dashboard
# # #         await post_access_log(
# # #             name=result.name,
# # #             method="face",
# # #             success=result.success,
# # #             image_url=image_url,
# # #         )

# # from __future__ import annotations
# # import asyncio
# # from pathlib import Path
# # from communication.uart_protocol import frame_unlock_door, frame_enable_keypad
# # from communication.cloud_uploader import upload
# # from communication.api_client import post_access_log
# # from logging_module.event_logger import log_app, log_access

# # class DoorController:
# #     def __init__(self, uart_handler):
# #         self._uart = uart_handler

# #     async def handle_detection_result(self, result):
# #         """Hàm này được gọi bởi PresenceDetector khi đã chốt kết quả"""
# #         if result.recognized:
# #             await self._uart.send(frame_unlock_door())
# #             log_app("info", f"Door unlocked for {result.name}")
# #         else:
# #             await self._uart.send(frame_enable_keypad())
# #             log_app("info", "Face failed - Keypad enabled")

# #         # Chạy tác vụ ghi log và upload ngầm để không làm chậm việc mở cửa
# #         asyncio.create_task(self._do_logging(result))

# #     async def _do_logging(self, result):
# #         image_url = ""
# #         if result.image_path:
# #             url = await upload(Path(result.image_path))
# #             image_url = url or ""

# #         log_access(name=result.name, method="face", success=result.recognized, image_url=image_url)
# #         await post_access_log(name=result.name, method="face", success=result.recognized, image_url=image_url)



# """
# pi4/control/door_controller.py
# Mục đích: Điều khiển logic mở/khóa cửa và bật bàn phím.
# """
# from __future__ import annotations
# import asyncio
# from pathlib import Path

# # Đã bổ sung frame_lock_door để khóa cửa từ xa
# from communication.uart_protocol import frame_unlock_door, frame_enable_keypad, frame_lock_door
# from communication.cloud_uploader import upload
# from communication.api_client import post_access_log
# from logging_module.event_logger import log_app, log_access

# class DoorController:
#     def __init__(self, uart_handler):
#         self._uart = uart_handler

#     # ✅ VÁ LỖI BUG #3: Hàm unlock() để API từ Web có thể gọi
#     async def unlock(self):
#         """Mở cửa từ remote Web Dashboard."""
#         await self._uart.send(frame_unlock_door())
#         log_app("info", "Door unlocked via remote command")

#     # ✅ VÁ LỖI BUG #3: Hàm lock() để API từ Web có thể gọi
#     async def lock(self):
#         """Khóa cửa từ remote Web Dashboard."""
#         await self._uart.send(frame_lock_door())
#         log_app("info", "Door locked via remote command")

#     async def handle_detection_result(self, result):
#         """Hàm này được gọi bởi PresenceDetector khi đã chốt kết quả quét mặt"""
#         if result.recognized:
#             await self._uart.send(frame_unlock_door())
#             log_app("info", f"Door unlocked for {result.name}")
#         else:
#             await self._uart.send(frame_enable_keypad())
#             log_app("info", "Face failed - Keypad enabled")

#         # Chạy tác vụ ghi log và upload ngầm để không làm chậm việc mở cửa
#         asyncio.create_task(self._do_logging(result))

#     async def _do_logging(self, result):
#         image_url = ""
#         if result.image_path:
#             url = await upload(Path(result.image_path))
#             image_url = url or ""

#         # Ghi log thẻ nhớ
#         log_access(name=result.name, method="face", success=result.recognized, image_url=image_url)
#         # Bắn log lên Server
#         await post_access_log(name=result.name, method="face", success=result.recognized, image_url=image_url)



"""
pi4/control/door_controller.py
Mục đích: Điều khiển logic mở/khóa cửa và bật bàn phím.
[VÁ LỖI HIGH]: Bổ sung cơ chế chờ ACK cho các lệnh quan trọng.
"""
from __future__ import annotations
import asyncio
from pathlib import Path

from communication.uart_protocol import frame_unlock_door, frame_enable_keypad, frame_lock_door
from communication.cloud_uploader import upload
from communication.api_client import post_access_log
from logging_module.event_logger import log_app, log_access

class DoorController:
    def __init__(self, uart_handler):
        self._uart = uart_handler

    # ✅ VÁ LỖI BUG #3: Hàm unlock() để API từ Web có thể gọi
    async def unlock(self):
        """Mở cửa từ remote Web Dashboard."""
        # [SỬA]: Yêu cầu chờ phản hồi ACK_UNLOCK từ STM32
        success = await self._uart.send(frame_unlock_door(), expect_ack="ACK_UNLOCK")
        if success:
            log_app("info", "Door unlocked via remote command (ACK received)")
        else:
            log_app("warning", "Remote unlock command sent, but NO ACK received")

    # ✅ VÁ LỖI BUG #3: Hàm lock() để API từ Web có thể gọi
    async def lock(self):
        """Khóa cửa từ remote Web Dashboard."""
        # [SỬA]: Yêu cầu chờ phản hồi ACK_LOCK từ STM32
        success = await self._uart.send(frame_lock_door(), expect_ack="ACK_LOCK")
        if success:
             log_app("info", "Door locked via remote command (ACK received)")
        else:
             log_app("warning", "Remote lock command sent, but NO ACK received")

    async def handle_detection_result(self, result):
        """Hàm này được gọi bởi PresenceDetector khi đã chốt kết quả quét mặt"""
        if result.recognized:
            # [SỬA]: Yêu cầu chờ phản hồi ACK_UNLOCK từ STM32
            success = await self._uart.send(frame_unlock_door(), expect_ack="ACK_UNLOCK")
            if success:
                log_app("info", f"Door unlocked for {result.name} (ACK received)")
            else:
                 log_app("warning", f"Unlock command sent for {result.name}, but NO ACK received")
        else:
            # [SỬA]: Yêu cầu chờ phản hồi ACK_KEYPAD từ STM32
            success = await self._uart.send(frame_enable_keypad(), expect_ack="ACK_KEYPAD")
            if success:
                log_app("info", "Face failed - Keypad enabled (ACK received)")
            else:
                log_app("warning", "Face failed - Keypad enable command sent, but NO ACK received")

        # Chạy tác vụ ghi log và upload ngầm để không làm chậm việc mở cửa
        asyncio.create_task(self._do_logging(result))

    async def _do_logging(self, result):
        image_url = ""
        if result.image_path:
            url = await upload(Path(result.image_path))
            image_url = url or ""

        # Ghi log thẻ nhớ
        log_access(name=result.name, method="face", success=result.recognized, image_url=image_url)
        # Bắn log lên Server
        await post_access_log(name=result.name, method="face", success=result.recognized, image_url=image_url)
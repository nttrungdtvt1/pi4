# # # control/alarm_controller.py
# # """
# # Quản lý trạng thái alarm.
# # Theo dõi sự kiện ALARM_ACTIVE, gửi cảnh báo lên Web,
# # và lắng nghe lệnh CMD_STOP_ALARM từ dashboard.
# # """
# # from __future__ import annotations

# # import asyncio
# # from config.constants import ALARM_DURATION_SECONDS, CMD_STOP_ALARM
# # from communication.uart_protocol import frame_stop_alarm
# # from communication.api_client import post_alarm, get_pending_command
# # from logging_module.event_logger import log_app, log_event, EventType


# # class AlarmController:
# #     def __init__(self, uart_handler):
# #         self._uart    = uart_handler
# #         self._active  = False
# #         self._task: asyncio.Task | None = None

# #     async def start_alarm(self, image_url: str = "") -> None:
# #         """Gọi khi nhận ALARM_ACTIVE từ STM32."""
# #         if self._active:
# #             return

# #         self._active = True
# #         log_event(EventType.ALARM_ACTIVE, image_url=image_url)
# #         log_app("warning", "Alarm triggered! Spawning monitor task.")

# #         # Gửi cảnh báo lên Web ngay lập tức
# #         await post_alarm(reason="security_breach", image_url=image_url)

# #         # Spawn task theo dõi stop condition (chạy ngầm)
# #         self._task = asyncio.create_task(self._monitor_alarm())

# #     async def _monitor_alarm(self) -> None:
# #         """
# #         Chờ một trong hai điều kiện:
# #           1. Hết timeout ALARM_DURATION_SECONDS.
# #           2. Dashboard gửi CMD_STOP_ALARM.
# #         """
# #         elapsed = 0
# #         poll_interval = 5   # Cứ 5 giây đi hỏi Dashboard 1 lần

# #         try:
# #             while self._active and elapsed < ALARM_DURATION_SECONDS:
# #                 # Ngủ ngầm 5s, nếu bị stop_alarm() gọi cancel() thì sẽ quăng CancelledError tại đây
# #                 await asyncio.sleep(poll_interval)
# #                 elapsed += poll_interval

# #                 # Đi hỏi Web xem chủ nhà có bấm nút "Tắt còi" trên Dashboard không
# #                 cmd = await get_pending_command()
# #                 if cmd == CMD_STOP_ALARM:
# #                     log_app("info", "CMD_STOP_ALARM received from dashboard")
# #                     await self.stop_alarm()
# #                     return

# #             # Nếu vòng lặp tự kết thúc do hết thời gian (Timeout)
# #             if self._active:
# #                 log_app("info", "Alarm auto-stopped after timeout", seconds=ALARM_DURATION_SECONDS)
# #                 await self.stop_alarm()

# #         except asyncio.CancelledError:
# #             log_app("debug", "Alarm monitor task was cancelled preemptively.")
# #             # Task bị hủy gọn gàng, không làm gì thêm
# #             raise

# #     async def stop_alarm(self) -> None:
# #         """Tắt còi và dọn dẹp các tác vụ đang chạy ngầm."""
# #         if not self._active:
# #             return

# #         self._active = False

# #         # Hủy task monitor nếu nó vẫn đang rình rập ngầm
# #         if self._task and not self._task.done():
# #             self._task.cancel()

# #         # Gửi lệnh tắt còi xuống mạch STM32
# #         await self._uart.send(frame_stop_alarm())
# #         log_event(EventType.ALARM_STOPPED)
# #         log_app("info", "Alarm has been completely stopped.")

# #     @property
# #     def is_active(self) -> bool:
# #         return self._active



# # pi4/control/alarm_controller.py
# """
# Quản lý trạng thái alarm.
# Theo dõi sự kiện ALARM_ACTIVE, gửi cảnh báo lên Web,
# và lắng nghe lệnh CMD_STOP_ALARM từ dashboard.
# """
# from __future__ import annotations

# import asyncio
# from config.constants import ALARM_DURATION_SECONDS, CMD_STOP_ALARM
# from communication.uart_protocol import frame_stop_alarm
# from communication.api_client import post_alarm, get_pending_command
# from logging_module.event_logger import log_app, log_event, EventType


# class AlarmController:
#     def __init__(self, uart_handler):
#         self._uart    = uart_handler
#         self._active  = False
#         self._task: asyncio.Task | None = None

#     # ✅ VÁ LỖI BUG #2: Bổ sung 2 hàm alias (start và stop) để tương thích
#     # với lời gọi từ main.py, triệt tiêu hoàn toàn lỗi AttributeError gây crash.
#     async def start(self, image_url: str = "") -> None:
#         await self.start_alarm(image_url)

#     async def stop(self) -> None:
#         await self.stop_alarm()

#     async def start_alarm(self, image_url: str = "") -> None:
#         """Gọi khi nhận ALARM_ACTIVE từ STM32."""
#         if self._active:
#             return

#         self._active = True
#         log_event(EventType.ALARM_ACTIVE, image_url=image_url)
#         log_app("warning", "Alarm triggered! Spawning monitor task.")

#         # Gửi cảnh báo lên Web ngay lập tức
#         await post_alarm(reason="security_breach", image_url=image_url)

#         # Spawn task theo dõi stop condition (chạy ngầm)
#         self._task = asyncio.create_task(self._monitor_alarm())

#     async def _monitor_alarm(self) -> None:
#         """
#         Chờ một trong hai điều kiện:
#           1. Hết timeout ALARM_DURATION_SECONDS.
#           2. Dashboard gửi CMD_STOP_ALARM.
#         """
#         elapsed = 0
#         poll_interval = 5   # Cứ 5 giây đi hỏi Dashboard 1 lần

#         try:
#             while self._active and elapsed < ALARM_DURATION_SECONDS:
#                 # Ngủ ngầm 5s, nếu bị stop_alarm() gọi cancel() thì sẽ quăng CancelledError tại đây
#                 await asyncio.sleep(poll_interval)
#                 elapsed += poll_interval

#                 # Đi hỏi Web xem chủ nhà có bấm nút "Tắt còi" trên Dashboard không
#                 cmd = await get_pending_command()

#                 # ĐÃ SỬA LỖI [CRITICAL-7]: Thêm .strip() để gọt bỏ khoảng trắng/newline thừa
#                 if cmd and cmd.strip() == CMD_STOP_ALARM.strip():
#                     log_app("info", "CMD_STOP_ALARM received from dashboard")
#                     await self.stop_alarm()
#                     return

#             # Nếu vòng lặp tự kết thúc do hết thời gian (Timeout)
#             if self._active:
#                 log_app("info", "Alarm auto-stopped after timeout", seconds=ALARM_DURATION_SECONDS)
#                 await self.stop_alarm()

#         except asyncio.CancelledError:
#             log_app("debug", "Alarm monitor task was cancelled preemptively.")
#             # Task bị hủy gọn gàng, không làm gì thêm
#             raise

#     async def stop_alarm(self) -> None:
#         """Tắt còi và dọn dẹp các tác vụ đang chạy ngầm."""
#         if not self._active:
#             return

#         self._active = False

#         # Hủy task monitor nếu nó vẫn đang rình rập ngầm
#         if self._task and not self._task.done():
#             self._task.cancel()

#         # Gửi lệnh tắt còi xuống mạch STM32
#         await self._uart.send(frame_stop_alarm())
#         log_event(EventType.ALARM_STOPPED)
#         log_app("info", "Alarm has been completely stopped.")

#     @property
#     def is_active(self) -> bool:
#         return self._active

"""
pi4/control/alarm_controller.py

Quản lý trạng thái alarm.
Theo dõi sự kiện ALARM_ACTIVE, gửi cảnh báo lên Web,
và lắng nghe lệnh CMD_STOP_ALARM từ dashboard.

[UPDATE]: Bổ sung thuộc tính `duration` để nhận cấu hình động từ Web.
"""
from __future__ import annotations

import asyncio
from config.constants import ALARM_DURATION_SECONDS, CMD_STOP_ALARM
from communication.uart_protocol import frame_stop_alarm
from communication.api_client import post_alarm, get_pending_command
from logging_module.event_logger import log_app, log_event, EventType


class AlarmController:
    def __init__(self, uart_handler):
        self._uart    = uart_handler
        self._active  = False
        self._task: asyncio.Task | None = None
        
        # ✅ CẤU HÌNH ĐỘNG: Lấy giá trị mặc định từ hằng số, nhưng có thể bị ghi đè bởi main.py
        self.duration = ALARM_DURATION_SECONDS

    # ✅ VÁ LỖI BUG #2: Bổ sung 2 hàm alias (start và stop) để tương thích
    # với lời gọi từ main.py, triệt tiêu hoàn toàn lỗi AttributeError gây crash.
    async def start(self, image_url: str = "") -> None:
        await self.start_alarm(image_url)

    async def stop(self) -> None:
        await self.stop_alarm()

    async def start_alarm(self, image_url: str = "") -> None:
        """Gọi khi nhận ALARM_ACTIVE từ STM32."""
        if self._active:
            return

        self._active = True
        log_event(EventType.ALARM_ACTIVE, image_url=image_url)
        log_app("warning", f"Alarm triggered! Spawning monitor task for {self.duration} seconds.")

        # Gửi cảnh báo lên Web ngay lập tức
        await post_alarm(reason="security_breach", image_url=image_url)

        # Spawn task theo dõi stop condition (chạy ngầm)
        self._task = asyncio.create_task(self._monitor_alarm())

    async def _monitor_alarm(self) -> None:
        """
        Chờ một trong hai điều kiện:
          1. Hết timeout self.duration (Cấu hình động từ Web).
          2. Dashboard gửi CMD_STOP_ALARM.
        """
        elapsed = 0
        poll_interval = 5   # Cứ 5 giây đi hỏi Dashboard 1 lần

        try:
            # ✅ SỬA: Đếm theo self.duration thay vì hằng số tĩnh
            while self._active and elapsed < self.duration:
                # Ngủ ngầm 5s, nếu bị stop_alarm() gọi cancel() thì sẽ quăng CancelledError tại đây
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                # Đi hỏi Web xem chủ nhà có bấm nút "Tắt còi" trên Dashboard không
                cmd = await get_pending_command()

                # ĐÃ SỬA LỖI [CRITICAL-7]: Thêm .strip() để gọt bỏ khoảng trắng/newline thừa
                if cmd and cmd.strip() == CMD_STOP_ALARM.strip():
                    log_app("info", "CMD_STOP_ALARM received from dashboard")
                    await self.stop_alarm()
                    return

            # Nếu vòng lặp tự kết thúc do hết thời gian (Timeout)
            if self._active:
                log_app("info", "Alarm auto-stopped after timeout", seconds=self.duration)
                await self.stop_alarm()

        except asyncio.CancelledError:
            log_app("debug", "Alarm monitor task was cancelled preemptively.")
            # Task bị hủy gọn gàng, không làm gì thêm
            raise

    async def stop_alarm(self) -> None:
        """Tắt còi và dọn dẹp các tác vụ đang chạy ngầm."""
        if not self._active:
            return

        self._active = False

        # Hủy task monitor nếu nó vẫn đang rình rập ngầm
        if self._task and not self._task.done():
            self._task.cancel()

        # Gửi lệnh tắt còi xuống mạch STM32
        await self._uart.send(frame_stop_alarm())
        log_event(EventType.ALARM_STOPPED)
        log_app("info", "Alarm has been completely stopped.")

    @property
    def is_active(self) -> bool:
        return self._active
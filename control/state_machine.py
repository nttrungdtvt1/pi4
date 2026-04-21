# # # # # control/state_machine.py
# # # # from __future__ import annotations

# # # # import asyncio
# # # # from enum import Enum
# # # # from logging_module.event_logger import log_app, log_event, EventType


# # # # class State(Enum):
# # # #     IDLE = "IDLE"
# # # #     RECOGNIZING = "RECOGNIZING"
# # # #     PASSWORD_MODE = "PASSWORD_MODE"
# # # #     ALARM = "ALARM"


# # # # class StateMachine:
# # # #     def __init__(self, event_queues, door_controller, alarm_controller):
# # # #         self._eq = event_queues
# # # #         self._door = door_controller
# # # #         self._alarm = alarm_controller
# # # #         self._state = State.IDLE

# # # #     async def run(self) -> None:
# # # #         """Vòng lặp vô tận duy trì State Machine."""
# # # #         log_app("info", "StateMachine started")
# # # #         while True:
# # # #             try:
# # # #                 if self._state == State.IDLE:
# # # #                     await self._state_idle()
# # # #                 elif self._state == State.RECOGNIZING:
# # # #                     await self._state_recognizing()
# # # #                 elif self._state == State.PASSWORD_MODE:
# # # #                     await self._state_password()
# # # #                 elif self._state == State.ALARM:
# # # #                     await self._state_alarm()
# # # #             except asyncio.CancelledError:
# # # #                 log_app("info", "StateMachine cancelled")
# # # #                 raise
# # # #             except Exception as exc:
# # # #                 log_event(EventType.SYSTEM_ERROR, detail=f"StateMachine fault: {exc}")
# # # #                 # Reset về IDLE an toàn nếu có lỗi không mong muốn
# # # #                 self._state = State.IDLE
# # # #                 await asyncio.sleep(1)

# # # #     async def _state_idle(self) -> None:
# # # #         """Chờ có người lại gần (Motion). Xóa các sự kiện cũ để tránh spam."""
# # # #         self._flush_queue(self._eq.motion)

# # # #         # Chờ đến khi có chuyển động thực sự
# # # #         await self._eq.motion.get()
# # # #         self._eq.motion.task_done() # Báo cáo đã tiêu thụ xong sự kiện

# # # #         log_app("info", "Transitioning to RECOGNIZING")
# # # #         self._state = State.RECOGNIZING

# # # #     async def _state_recognizing(self) -> None:
# # # #         """Gọi luồng nhận diện. Quyết định mở cửa hoặc bật bàn phím."""
# # # #         result = await self._door.run_recognition_cycle()

# # # #         if result.success:
# # # #             log_app("info", "Door opened via face. Cooling down 15s...")
# # # #             # Cooldown 15 giây để người dùng đi vào, tránh cảm biến kích hoạt lại
# # # #             await asyncio.sleep(15.0)
# # # #             self._state = State.IDLE
# # # #         else:
# # # #             self._state = State.PASSWORD_MODE

# # # #     async def _state_password(self) -> None:
# # # #         """
# # # #         Chờ STM32 gửi trạng thái:
# # # #         1. Mở bằng pass thành công -> Về IDLE
# # # #         2. Nhập sai pass -> Tiếp tục chờ
# # # #         3. Sai 3 lần (Alarm) -> Chuyển sang ALARM
# # # #         4. Timeout 30 giây không thao tác -> Về IDLE
# # # #         """
# # # #         log_app("info", "Waiting for password input...")

# # # #         t_open = asyncio.create_task(self._eq.door_opened.get())
# # # #         t_fail = asyncio.create_task(self._eq.pwd_failed.get())
# # # #         t_alarm = asyncio.create_task(self._eq.alarm.get())

# # # #         # Chờ 1 trong 3 queue có dữ liệu, tối đa 30s
# # # #         done, pending = await asyncio.wait(
# # # #             [t_open, t_fail, t_alarm],
# # # #             timeout=30.0,
# # # #             return_when=asyncio.FIRST_COMPLETED
# # # #         )

# # # #         # Hủy các task đang chờ để không leak bộ nhớ
# # # #         for task in pending:
# # # #             task.cancel()

# # # #         if not done:
# # # #             log_app("info", "Password mode timeout. Transitioning to IDLE")
# # # #             self._state = State.IDLE
# # # #             return

# # # #         # Gọi task_done() cho TẤT CẢ các task đã hoàn thành để dọn dẹp Queue
# # # #         for task in done:
# # # #             if task == t_open:
# # # #                 self._eq.door_opened.task_done()
# # # #             elif task == t_fail:
# # # #                 self._eq.pwd_failed.task_done()
# # # #             elif task == t_alarm:
# # # #                 self._eq.alarm.task_done()

# # # #         # Xét độ ưu tiên trạng thái nếu có nhiều sự kiện kích hoạt cùng 1 lúc (millisecond)
# # # #         if t_alarm in done:
# # # #             self._state = State.ALARM
# # # #         elif t_open in done:
# # # #             log_app("info", "Door opened via password. Cooling down 15s...")
# # # #             await asyncio.sleep(15.0) # Cooldown đóng cửa
# # # #             self._state = State.IDLE
# # # #         elif t_fail in done:
# # # #             # Nhập sai 1 lần, STM32 tự đếm. Pi vẫn ở lại state này chờ người dùng nhập tiếp
# # # #             log_app("info", "Password incorrect. Continuing in PASSWORD_MODE")

# # # #     async def _state_alarm(self) -> None:
# # # #         """Bật cảnh báo và chờ đến khi hết cảnh báo."""
# # # #         log_app("warning", "Transitioning to ALARM state")
# # # #         await self._alarm.start_alarm()

# # # #         # Chờ AlarmController tự tắt (qua timeout hoặc qua Web Dashboard)
# # # #         while self._alarm.is_active:
# # # #             await asyncio.sleep(1)

# # # #         # Dọn sạch các tín hiệu báo động còn sót lại để không bị kích hoạt kép
# # # #         self._flush_queue(self._eq.alarm)
# # # #         self._state = State.IDLE

# # # #     def _flush_queue(self, q: asyncio.Queue) -> None:
# # # #         """Dọn dẹp các sự kiện cũ bị kẹt trong queue."""
# # # #         while not q.empty():
# # # #             try:
# # # #                 q.get_nowait()
# # # #                 q.task_done()
# # # #             except asyncio.QueueEmpty:
# # # #                 break

# # # """
# # # control/state_machine.py

# # # Mục đích: Quản lý logic luồng sự kiện của toàn hệ thống.
# # # Nhận tín hiệu từ UART (STM32) và điều phối các bộ phận:
# # # - PIR Motion -> Gọi PresenceDetector để xử lý thông minh.
# # # - PIN Sync -> Cập nhật trạng thái mã PIN.
# # # - Door Events -> Ghi log trạng thái cửa.
# # # """

# # # from __future__ import annotations
# # # import asyncio
# # # from logging_module.event_logger import log_app

# # # class StateMachine:
# # #     def __init__(
# # #         self,
# # #         event_queues,
# # #         door_controller,
# # #         alarm_controller=None,
# # #         presence_detector=None # ✅ Thêm để nhận bộ não PresenceDetector
# # #     ):
# # #         self.event_queues = event_queues
# # #         self.door_controller = door_controller
# # #         self.alarm_controller = alarm_controller
# # #         self.presence_detector = presence_detector # ✅ Lưu vào biến class

# # #         self._running = False

# # #     async def run(self) -> None:
# # #         """Vòng lặp chính lắng nghe các sự kiện từ hàng đợi chuyên biệt."""
# # #         self._running = True
# # #         log_app("info", "StateMachine loop started và đang lắng nghe hàng đợi 'motion'.")

# # #         while self._running:
# # #             try:
# # #                 # ✅ SỬA TẠI ĐÂY: Lắng nghe trực tiếp từ hàng đợi motion
# # #                 # Khi có chuyển động, EventHandler sẽ đẩy giá trị True vào đây
# # #                 has_motion = await self.event_queues.motion.get()

# # #                 if has_motion:
# # #                     await self.handle_pir_event()

# # #                 # Giải phóng hàng đợi
# # #                 self.event_queues.motion.task_done()

# # #             except Exception as e:
# # #                 log_app("error", f"Error in StateMachine loop: {e}")
# # #                 await asyncio.sleep(1)

# # #     async def handle_pir_event(self):
# # #         """Xử lý khi cảm biến PIR báo có chuyển động."""
# # #         log_app("info", "[STATE] Nhận tín hiệu PIR -> Kích hoạt bộ não PresenceDetector")

# # #         if self.presence_detector:
# # #             # Gọi bộ não xử lý lọc nhiễu (WATCH -> STABILIZE -> SCAN)
# # #             await self.presence_detector.on_pir_triggered()
# # #         else:
# # #             log_app("warning", "[STATE] PresenceDetector chưa được khởi tạo!")

# # #     def stop(self):
# # #         """Dừng vòng lặp StateMachine."""
# # #         self._running = False



# # # # control/state_machine.py
# # # from __future__ import annotations

# # # import asyncio
# # # from enum import Enum
# # # from logging_module.event_logger import log_app, log_event, EventType


# # # class State(Enum):
# # #     IDLE = "IDLE"
# # #     RECOGNIZING = "RECOGNIZING"
# # #     PASSWORD_MODE = "PASSWORD_MODE"
# # #     ALARM = "ALARM"


# # # class StateMachine:
# # #     def __init__(self, event_queues, door_controller, alarm_controller):
# # #         self._eq = event_queues
# # #         self._door = door_controller
# # #         self._alarm = alarm_controller
# # #         self._state = State.IDLE

# # #     async def run(self) -> None:
# # #         """Vòng lặp vô tận duy trì State Machine."""
# # #         log_app("info", "StateMachine started")
# # #         while True:
# # #             try:
# # #                 if self._state == State.IDLE:
# # #                     await self._state_idle()
# # #                 elif self._state == State.RECOGNIZING:
# # #                     await self._state_recognizing()
# # #                 elif self._state == State.PASSWORD_MODE:
# # #                     await self._state_password()
# # #                 elif self._state == State.ALARM:
# # #                     await self._state_alarm()
# # #             except asyncio.CancelledError:
# # #                 log_app("info", "StateMachine cancelled")
# # #                 raise
# # #             except Exception as exc:
# # #                 log_event(EventType.SYSTEM_ERROR, detail=f"StateMachine fault: {exc}")
# # #                 # Reset về IDLE an toàn nếu có lỗi không mong muốn
# # #                 self._state = State.IDLE
# # #                 await asyncio.sleep(1)

# # #     async def _state_idle(self) -> None:
# # #         """Chờ có người lại gần (Motion). Xóa các sự kiện cũ để tránh spam."""
# # #         self._flush_queue(self._eq.motion)

# # #         # Chờ đến khi có chuyển động thực sự
# # #         await self._eq.motion.get()
# # #         self._eq.motion.task_done() # Báo cáo đã tiêu thụ xong sự kiện

# # #         log_app("info", "Transitioning to RECOGNIZING")
# # #         self._state = State.RECOGNIZING

# # #     async def _state_recognizing(self) -> None:
# # #         """Gọi luồng nhận diện. Quyết định mở cửa hoặc bật bàn phím."""
# # #         result = await self._door.run_recognition_cycle()

# # #         if result.success:
# # #             log_app("info", "Door opened via face. Cooling down 15s...")
# # #             # Cooldown 15 giây để người dùng đi vào, tránh cảm biến kích hoạt lại
# # #             await asyncio.sleep(15.0)
# # #             self._state = State.IDLE
# # #         else:
# # #             self._state = State.PASSWORD_MODE

# # #     async def _state_password(self) -> None:
# # #         """
# # #         Chờ STM32 gửi trạng thái:
# # #         1. Mở bằng pass thành công -> Về IDLE
# # #         2. Nhập sai pass -> Tiếp tục chờ
# # #         3. Sai 3 lần (Alarm) -> Chuyển sang ALARM
# # #         4. Timeout 30 giây không thao tác -> Về IDLE
# # #         """
# # #         log_app("info", "Waiting for password input...")

# # #         t_open = asyncio.create_task(self._eq.door_opened.get())
# # #         t_fail = asyncio.create_task(self._eq.pwd_failed.get())
# # #         t_alarm = asyncio.create_task(self._eq.alarm.get())

# # #         # Chờ 1 trong 3 queue có dữ liệu, tối đa 30s
# # #         done, pending = await asyncio.wait(
# # #             [t_open, t_fail, t_alarm],
# # #             timeout=30.0,
# # #             return_when=asyncio.FIRST_COMPLETED
# # #         )

# # #         # Hủy các task đang chờ để không leak bộ nhớ
# # #         for task in pending:
# # #             task.cancel()

# # #         if not done:
# # #             log_app("info", "Password mode timeout. Transitioning to IDLE")
# # #             self._state = State.IDLE
# # #             return

# # #         # Gọi task_done() cho TẤT CẢ các task đã hoàn thành để dọn dẹp Queue
# # #         for task in done:
# # #             if task == t_open:
# # #                 self._eq.door_opened.task_done()
# # #             elif task == t_fail:
# # #                 self._eq.pwd_failed.task_done()
# # #             elif task == t_alarm:
# # #                 self._eq.alarm.task_done()

# # #         # Xét độ ưu tiên trạng thái nếu có nhiều sự kiện kích hoạt cùng 1 lúc (millisecond)
# # #         if t_alarm in done:
# # #             self._state = State.ALARM
# # #         elif t_open in done:
# # #             log_app("info", "Door opened via password. Cooling down 15s...")
# # #             await asyncio.sleep(15.0) # Cooldown đóng cửa
# # #             self._state = State.IDLE
# # #         elif t_fail in done:
# # #             # Nhập sai 1 lần, STM32 tự đếm. Pi vẫn ở lại state này chờ người dùng nhập tiếp
# # #             log_app("info", "Password incorrect. Continuing in PASSWORD_MODE")

# # #     async def _state_alarm(self) -> None:
# # #         """Bật cảnh báo và chờ đến khi hết cảnh báo."""
# # #         log_app("warning", "Transitioning to ALARM state")
# # #         await self._alarm.start_alarm()

# # #         # Chờ AlarmController tự tắt (qua timeout hoặc qua Web Dashboard)
# # #         while self._alarm.is_active:
# # #             await asyncio.sleep(1)

# # #         # Dọn sạch các tín hiệu báo động còn sót lại để không bị kích hoạt kép
# # #         self._flush_queue(self._eq.alarm)
# # #         self._state = State.IDLE

# # #     def _flush_queue(self, q: asyncio.Queue) -> None:
# # #         """Dọn dẹp các sự kiện cũ bị kẹt trong queue."""
# # #         while not q.empty():
# # #             try:
# # #                 q.get_nowait()
# # #                 q.task_done()
# # #             except asyncio.QueueEmpty:
# # #                 break

# # """
# # control/state_machine.py

# # Mục đích: Quản lý logic luồng sự kiện của toàn hệ thống.
# # Nhận tín hiệu từ UART (STM32) và điều phối các bộ phận:
# # - PIR Motion -> Gọi PresenceDetector để xử lý thông minh.
# # - PIN Sync -> Cập nhật trạng thái mã PIN.
# # - Door Events -> Ghi log trạng thái cửa.
# # """

# # from __future__ import annotations
# # import asyncio
# # from logging_module.event_logger import log_app

# # class StateMachine:
# #     def __init__(
# #         self,
# #         event_queues,
# #         door_controller,
# #         alarm_controller=None,
# #         presence_detector=None # ✅ Thêm để nhận bộ não PresenceDetector
# #     ):
# #         self.event_queues = event_queues
# #         self.door_controller = door_controller
# #         self.alarm_controller = alarm_controller
# #         self.presence_detector = presence_detector # ✅ Lưu vào biến class

# #         self._running = False

# #     async def run(self) -> None:
# #         """Vòng lặp chính lắng nghe các sự kiện từ hàng đợi chuyên biệt."""
# #         self._running = True
# #         log_app("info", "StateMachine loop started và đang lắng nghe hàng đợi 'motion'.")

# #         while self._running:
# #             try:
# #                 # ✅ SỬA TẠI ĐÂY: Lắng nghe trực tiếp từ hàng đợi motion
# #                 # Khi có chuyển động, EventHandler sẽ đẩy giá trị True vào đây
# #                 has_motion = await self.event_queues.motion.get()

# #                 if has_motion:
# #                     await self.handle_pir_event()

# #                 # Giải phóng hàng đợi
# #                 self.event_queues.motion.task_done()

# #             except Exception as e:
# #                 log_app("error", f"Error in StateMachine loop: {e}")
# #                 await asyncio.sleep(1)

# #     async def handle_pir_event(self):
# #         """Xử lý khi cảm biến PIR báo có chuyển động."""
# #         log_app("info", "[STATE] Nhận tín hiệu PIR -> Kích hoạt bộ não PresenceDetector")

# #         if self.presence_detector:
# #             # Gọi bộ não xử lý lọc nhiễu (WATCH -> STABILIZE -> SCAN)
# #             await self.presence_detector.on_pir_triggered()
# #         else:
# #             log_app("warning", "[STATE] PresenceDetector chưa được khởi tạo!")

# #     def stop(self):
# #         """Dừng vòng lặp StateMachine."""
# #         self._running = False



# """
# control/state_machine.py

# Mục đích: Quản lý logic luồng sự kiện của toàn hệ thống.
# Nhận tín hiệu từ UART (STM32) và điều phối các bộ phận:
# - Lắng nghe TẤT CẢ các queue để tránh rò rỉ bộ nhớ.
# - Quản lý cơ chế Khóa PIR (Grace Period) để chống nhiễu khi đang nhập PIN.
# """

# from __future__ import annotations
# import asyncio
# from logging_module.event_logger import log_app

# class StateMachine:
#     def __init__(
#         self,
#         event_queues,
#         door_controller,
#         alarm_controller=None,
#         presence_detector=None
#     ):
#         self.event_queues = event_queues
#         self.door_controller = door_controller
#         self.alarm_controller = alarm_controller
#         self.presence_detector = presence_detector

#         self._running = False
#         self._pir_lock_until = 0.0  # ✅ Cờ khóa PIR để tránh xung đột với STM32

#     async def run(self) -> None:
#         """Vòng lặp chính lắng nghe đồng thời TẤT CẢ các sự kiện từ UART."""
#         self._running = True
#         log_app("info", "StateMachine loop started và đang lắng nghe toàn bộ event queues.")

#         while self._running:
#             try:
#                 # 1. Đóng gói các hàm get() thành Task để chờ đồng thời
#                 tasks_map = {
#                     asyncio.create_task(self.event_queues.motion.get()): "motion",
#                     asyncio.create_task(self.event_queues.pwd_failed.get()): "pwd_failed",
#                     asyncio.create_task(self.event_queues.door_opened_pwd.get()): "door_opened_pwd",
#                     asyncio.create_task(self.event_queues.door_opened.get()): "door_opened",
#                     asyncio.create_task(self.event_queues.alarm.get()): "alarm"
#                 }

#                 # 2. Chờ sự kiện ĐẦU TIÊN xuất hiện
#                 done, pending = await asyncio.wait(
#                     tasks_map.keys(),
#                     return_when=asyncio.FIRST_COMPLETED
#                 )

#                 # 3. Hủy các task chưa hoàn thành để làm sạch bộ nhớ ở vòng lặp sau
#                 for t in pending:
#                     t.cancel()

#                 now = asyncio.get_event_loop().time()

#                 # 4. Phân loại và xử lý sự kiện
#                 for task in done:
#                     event_type = tasks_map[task]
                    
#                     try:
#                         result = await task
#                     except asyncio.CancelledError:
#                         continue

#                     # --- XỬ LÝ TỪNG LOẠI SỰ KIỆN ---
#                     if event_type == "alarm":
#                         self.event_queues.alarm.task_done()
#                         log_app("warning", "[STATE] Nhận tín hiệu ALARM từ phần cứng!")
#                         if self.alarm_controller:
#                             await self.alarm_controller.start()
#                         self._pir_lock_until = now + 180.0  # Khóa PIR 3 phút khi báo động

#                     elif event_type == "pwd_failed":
#                         self.event_queues.pwd_failed.task_done()
#                         log_app("warning", "[STATE] Nhập sai PIN! Khóa PIR thêm 30s để thao tác.")
#                         self._pir_lock_until = now + 30.0

#                     elif event_type == "door_opened_pwd":
#                         self.event_queues.door_opened_pwd.task_done()
#                         log_app("info", "[STATE] Mở cửa bằng mã PIN thành công.")
#                         self._pir_lock_until = now + 15.0  # Cooldown 15s để người đi qua

#                     elif event_type == "door_opened":
#                         self.event_queues.door_opened.task_done()
#                         log_app("info", "[STATE] Mở cửa bằng Web/Nút bấm thành công.")
#                         self._pir_lock_until = now + 15.0

#                     elif event_type == "motion":
#                         self.event_queues.motion.task_done()
#                         if result:
#                             is_alarm = self.alarm_controller and self.alarm_controller.is_active
#                             is_locked = now < self._pir_lock_until

#                             if is_alarm or is_locked:
#                                 log_app("debug", "[STATE] Đã bỏ qua PIR (Hệ thống đang bận ALARM/PIN)")
#                             else:
#                                 # Bắt đầu luồng dò mặt và lập tức khóa PIR 30 giây để nhường quyền kiểm soát
#                                 self._pir_lock_until = now + 30.0
#                                 await self.handle_pir_event()

#             except Exception as e:
#                 log_app("error", f"Error in StateMachine loop: {e}")
#                 await asyncio.sleep(1)

#     async def handle_pir_event(self):
#         """Xử lý khi cảm biến PIR báo có chuyển động."""
#         log_app("info", "[STATE] Nhận tín hiệu PIR hợp lệ -> Kích hoạt PresenceDetector")

#         if self.presence_detector:
#             # Gọi bộ não xử lý lọc nhiễu (WATCH -> STABILIZE -> SCAN)
#             await self.presence_detector.on_pir_triggered()
#         else:
#             log_app("warning", "[STATE] PresenceDetector chưa được khởi tạo!")

#     def stop(self):
#         """Dừng vòng lặp StateMachine."""
#         self._running = False



"""
control/state_machine.py

Mục đích: Quản lý logic luồng sự kiện của toàn hệ thống.
Nhận tín hiệu từ UART (STM32) và điều phối các bộ phận.

[FIX]: Khắc phục lỗi AttributeError khi Queue không tồn tại.
[OPTIMIZE]: Cải tiến vòng lặp Task Polling để chống lỗi "nuốt sự kiện" (Event Leak) khi hủy Task.
"""

from __future__ import annotations
import asyncio
from logging_module.event_logger import log_app

class StateMachine:
    def __init__(
        self,
        event_queues,
        door_controller,
        alarm_controller=None,
        presence_detector=None
    ):
        self.event_queues = event_queues
        self.door_controller = door_controller
        self.alarm_controller = alarm_controller
        self.presence_detector = presence_detector

        self._running = False
        self._pir_lock_until = 0.0  # Cờ khóa PIR để tránh xung đột với STM32

    async def run(self) -> None:
        """Vòng lặp chính lắng nghe đồng thời TẤT CẢ các sự kiện từ UART."""
        self._running = True
        log_app("info", "StateMachine loop started và đang lắng nghe toàn bộ event queues.")

        # ✅ TỐI ƯU CẤP CAO: Lưu giữ các Task đang chờ để KHÔNG BỊ HỦY (Cancel) nhầm, 
        # tránh tình trạng "nuốt sự kiện" (Event Loss) khi có nhiều tín hiệu gửi lên cùng lúc.
        pending_tasks = {}

        def _listen_to_queue(q_name: str):
            """Hàm helper kiểm tra an toàn: Chỉ tạo Task lắng nghe nếu queue thực sự tồn tại."""
            if hasattr(self.event_queues, q_name):
                q = getattr(self.event_queues, q_name)
                task = asyncio.create_task(q.get())
                pending_tasks[task] = (q_name, q)

        # Nạp các hàng đợi vào hệ thống (An toàn tuyệt đối kể cả khi bị thiếu biến)
        _listen_to_queue("motion")
        _listen_to_queue("pwd_failed")
        _listen_to_queue("door_opened_pwd")
        _listen_to_queue("door_opened")
        _listen_to_queue("alarm")

        while self._running:
            try:
                if not pending_tasks:
                    log_app("warning", "[STATE] Không có queue nào để lắng nghe! Nghỉ 1s...")
                    await asyncio.sleep(1)
                    continue

                # 1. Chờ sự kiện ĐẦU TIÊN xuất hiện (Tuyệt đối KHÔNG HỦY các pending tasks)
                done, _ = await asyncio.wait(
                    pending_tasks.keys(),
                    return_when=asyncio.FIRST_COMPLETED
                )

                now = asyncio.get_event_loop().time()

                # 2. Xử lý các sự kiện đã hoàn thành
                for task in done:
                    # Lấy thông tin queue và loại bỏ task cũ khỏi danh sách pending
                    q_name, q = pending_tasks.pop(task) 
                    
                    try:
                        result = task.result()
                    except asyncio.CancelledError:
                        continue
                    except Exception as exc:
                        log_app("error", f"Lỗi đọc queue {q_name}: {exc}")
                        # Vẫn phải tạo lại task để không bị mù queue này ở tương lai
                        _listen_to_queue(q_name)
                        continue

                    # Đánh dấu queue đã giải phóng 1 item
                    q.task_done()

                    # --- XỬ LÝ TỪNG LOẠI SỰ KIỆN ---
                    if q_name == "alarm":
                        log_app("warning", "[STATE] Nhận tín hiệu ALARM từ phần cứng!")
                        if self.alarm_controller:
                            await self.alarm_controller.start()
                        self._pir_lock_until = now + 180.0  # Khóa PIR 3 phút khi báo động

                    elif q_name == "pwd_failed":
                        log_app("warning", "[STATE] Nhập sai PIN! Khóa PIR thêm 30s để thao tác.")
                        self._pir_lock_until = now + 30.0

                    elif q_name == "door_opened_pwd":
                        log_app("info", "[STATE] Mở cửa bằng mã PIN thành công.")
                        self._pir_lock_until = now + 15.0  # Cooldown 15s để người đi qua

                    elif q_name == "door_opened":
                        log_app("info", "[STATE] Mở cửa bằng Web/Nút bấm thành công.")
                        self._pir_lock_until = now + 15.0

                    elif q_name == "motion":
                        if result: # result chính là giá trị lấy ra từ queue (True)
                            is_alarm = self.alarm_controller and self.alarm_controller.is_active
                            is_locked = now < self._pir_lock_until

                            if is_alarm or is_locked:
                                log_app("debug", "[STATE] Đã bỏ qua PIR (Hệ thống đang bận ALARM/PIN)")
                            else:
                                # Bắt đầu luồng dò mặt và lập tức khóa PIR 30 giây để nhường quyền kiểm soát
                                self._pir_lock_until = now + 30.0
                                await self.handle_pir_event()

                    # 3. CHỈ MẤU CHỐT: Tạo task MỚI duy nhất cho queue vừa xử lý xong 
                    # để tiếp tục vòng lặp lắng nghe, các queue khác vẫn đang chờ nguyên vẹn.
                    _listen_to_queue(q_name)

            except Exception as e:
                log_app("error", f"Error in StateMachine loop: {e}")
                await asyncio.sleep(1)

    async def handle_pir_event(self):
        """Xử lý khi cảm biến PIR báo có chuyển động."""
        log_app("info", "[STATE] Nhận tín hiệu PIR hợp lệ -> Kích hoạt PresenceDetector")

        if self.presence_detector:
            # Gọi bộ não xử lý lọc nhiễu (WATCH -> STABILIZE -> SCAN)
            await self.presence_detector.on_pir_triggered()
        else:
            log_app("warning", "[STATE] PresenceDetector chưa được khởi tạo!")

    def stop(self):
        """Dừng vòng lặp StateMachine."""
        self._running = False
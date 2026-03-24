# # control/event_handler.py
# from __future__ import annotations

# import asyncio

# from communication.uart_protocol import classify_response
# from logging_module.event_logger import log_app, log_event, EventType


# class EventQueues:
#     """
#     Tập hợp các hàng đợi chuyên biệt.
#     Mô hình Pub/Sub nội bộ: EventHandler là Publisher,
#     StateMachine và AlarmController là Subscribers.
#     """
#     def __init__(self):
#         self.motion:       asyncio.Queue[bool] = asyncio.Queue()
#         self.door_opened:  asyncio.Queue[str]  = asyncio.Queue()
#         self.pwd_failed:   asyncio.Queue[None] = asyncio.Queue()
#         self.alarm:        asyncio.Queue[None] = asyncio.Queue()


# class EventHandler:
#     def __init__(self, uart_queue: asyncio.Queue[str], event_queues: EventQueues):
#         self._uart_q  = uart_queue
#         self._evqs    = event_queues

#     async def dispatch_loop(self) -> None:
#         """
#         Vòng lặp định tuyến (Router Loop).
#         Lấy chuỗi raw từ UART Queue, phân tích và đẩy vào đúng Event Queue con.
#         """
#         log_app("info", "EventHandler dispatch loop started")

#         while True:
#             try:
#                 # Lấy payload thô từ UART
#                 payload: str = await self._uart_q.get()

#                 # Bọc try...finally để đảm bảo luôn gọi task_done() cho _uart_q
#                 try:
#                     key = classify_response(payload)

#                     if key == "motion":
#                         log_event(EventType.MOTION_DETECTED)
#                         await self._evqs.motion.put(True)

#                     elif key == "door_opened":
#                         log_event(EventType.DOOR_OPENED, method="face")
#                         await self._evqs.door_opened.put("face")

#                     elif key == "door_opened_pwd":
#                         log_event(EventType.DOOR_OPENED_PWD, method="password")
#                         await self._evqs.door_opened.put("password")

#                     elif key == "password_failed":
#                         log_event(EventType.PASSWORD_FAILED)
#                         await self._evqs.pwd_failed.put(None)

#                     elif key == "alarm_active":
#                         log_event(EventType.ALARM_ACTIVE)
#                         await self._evqs.alarm.put(None)

#                     else:
#                         log_app("debug", "Unknown or unclassified UART payload", payload=payload)

#                 finally:
#                     # Báo cáo đã xử lý xong gói tin UART này (Giải phóng queue)
#                     self._uart_q.task_done()

#             except asyncio.CancelledError:
#                 log_app("info", "EventHandler dispatch loop cancelled")
#                 raise
#             except Exception as exc:
#                 log_event(EventType.SYSTEM_ERROR, detail=f"EventHandler loop error: {exc}")



# control/event_handler.py
from __future__ import annotations

import asyncio

from communication.uart_protocol import classify_response
from logging_module.event_logger import log_app, log_event, EventType


class EventQueues:
    """
    Tập hợp các hàng đợi chuyên biệt.
    Mô hình Pub/Sub nội bộ: EventHandler là Publisher,
    StateMachine và AlarmController là Subscribers.
    """
    def __init__(self):
        self.motion:       asyncio.Queue[bool] = asyncio.Queue()
        self.door_opened:  asyncio.Queue[str]  = asyncio.Queue()
        self.pwd_failed:   asyncio.Queue[None] = asyncio.Queue()
        self.alarm:        asyncio.Queue[None] = asyncio.Queue()


class EventHandler:
    def __init__(self, uart_queue: asyncio.Queue[str], event_queues: EventQueues):
        self._uart_q  = uart_queue
        self._evqs    = event_queues

    async def dispatch_loop(self) -> None:
        """
        Vòng lặp định tuyến (Router Loop).
        Lấy chuỗi raw từ UART Queue, phân tích và đẩy vào đúng Event Queue con.
        """
        log_app("info", "EventHandler dispatch loop started")

        while True:
            try:
                # Lấy payload thô từ UART
                payload: str = await self._uart_q.get()

                # Bọc try...finally để đảm bảo luôn gọi task_done() cho _uart_q
                try:
                    key = classify_response(payload)

                    if key == "motion":
                        log_event(EventType.MOTION_DETECTED)
                        await self._evqs.motion.put(True)

                    elif key == "door_opened":
                        log_event(EventType.DOOR_OPENED, method="face")
                        await self._evqs.door_opened.put("face")

                    elif key == "door_opened_pwd":
                        log_event(EventType.DOOR_OPENED_PWD, method="password")
                        await self._evqs.door_opened.put("password")

                    elif key == "password_failed":
                        log_event(EventType.PASSWORD_FAILED)
                        await self._evqs.pwd_failed.put(None)

                    elif key == "alarm_active":
                        log_event(EventType.ALARM_ACTIVE)
                        await self._evqs.alarm.put(None)

                    else:
                        log_app("debug", "Unknown or unclassified UART payload", payload=payload)

                finally:
                    # Báo cáo đã xử lý xong gói tin UART này (Giải phóng queue)
                    self._uart_q.task_done()

            except asyncio.CancelledError:
                log_app("info", "EventHandler dispatch loop cancelled")
                raise
            except Exception as exc:
                log_event(EventType.SYSTEM_ERROR, detail=f"EventHandler loop error: {exc}")

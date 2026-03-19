# # # main.py
# # """
# # Entry point của hệ thống Smart Door trên Raspberry Pi.
# # Khởi chạy tất cả các dịch vụ ngầm (background tasks) và State Machine.
# # Đã tích hợp cơ chế Retry Upload Ảnh thông minh (Offline Sync).
# # Tích hợp Live Stream Camera (MJPEG Feed) cho Dashboard Web.
# # """

# # from __future__ import annotations
# # import asyncio
# # import sys
# # from pathlib import Path

# # from aiohttp import web
# # import cv2

# # # Đảm bảo import path đúng khi chạy từ thư mục gốc
# # sys.path.insert(0, str(Path(__file__).resolve().parent))

# # from recognition.enroll_face import enroll
# # from config.settings import settings
# # from logging_module.event_logger import log_app, log_event, EventType

# # from communication.uart_handler import UartHandler
# # from communication.api_client import heartbeat_loop
# # from communication.cloud_uploader import upload_pending
# # from communication.pin_sync_service import PinSyncService, poll_pin_changes

# # from control.event_handler import EventQueues, EventHandler
# # from control.door_controller import DoorController
# # from control.alarm_controller import AlarmController
# # from control.state_machine import StateMachine

# # # Thêm import CameraManager để lấy luồng video
# # from vision.camera_manager import CameraManager


# # # =====================================================================
# # # VÒNG LẶP CHẠY NGẦM ĐỂ UPLOAD LẠI ẢNH BỊ KẸT (OFFLINE SYNC)
# # # =====================================================================
# # async def auto_upload_pending_loop():
# #     """Cứ mỗi 15 giây, kiểm tra xem có ảnh nào chụp lúc mất mạng không."""
# #     while True:
# #         try:
# #             await upload_pending()
# #         except Exception as e:
# #             log_app("error", f"Lỗi trong vòng lặp upload bù ảnh: {e}")
# #         # Đợi 15 giây rồi kiểm tra lại (không làm nặng máy)
# #         await asyncio.sleep(15)


# # async def async_main() -> None:
# #     # 1. Khởi tạo cấu trúc thư mục cần thiết
# #     settings.ensure_dirs()
# #     log_app("info", "System starting...")
# #     log_event(EventType.SYSTEM_START)

# #     # 2. Upload lại các ảnh bị kẹt do rớt mạng (Chạy 1 lần lúc khởi động)
# #     await upload_pending()

# #     # =========================================================================
# #     # 3. KHỞI TẠO TÀI NGUYÊN DÙNG CHUNG (GLOBAL RESOURCES)
# #     # Khởi tạo CameraManager và BẬT NÓ LÊN LUN ĐỂ CHẠY XUYÊN SUỐT DỰ ÁN
# #     # Đảm bảo LiveStream mượt mà 24/24 và AI có thể chụp ảnh ngay lập tức khi PIR gọi
# #     # =========================================================================
# #     shared_camera = CameraManager()
# #     await shared_camera.camera_on() # Mở mắt cho hệ thống ngay từ đầu

# #     # 4. Khởi tạo các hàng đợi (Queues)
# #     uart_rx_queue: asyncio.Queue[str] = asyncio.Queue()
# #     pin_sync_queue: asyncio.Queue[str] = asyncio.Queue()
# #     event_queues = EventQueues()

# #     # 5. Khởi tạo các Core Handlers & Controllers
# #     uart = UartHandler()
# #     try:
# #         uart.connect()
# #     except Exception as e:
# #         log_app("error", f"Failed to connect UART: {e}. Exiting.")
# #         sys.exit(1)

# #     event_dispatcher = EventHandler(uart_queue=uart_rx_queue, event_queues=event_queues)

# #     # Tiêm (Inject) shared_camera vào DoorController để dùng chung
# #     # Khi PIR báo hiệu (qua UART), DoorController sẽ trích xuất 1 frame từ camera này đem cho AI
# #     door_ctrl = DoorController(uart_handler=uart)
# #     door_ctrl._camera = shared_camera

# #     alarm_ctrl = AlarmController(uart_handler=uart)
# #     state_machine = StateMachine(
# #         event_queues=event_queues,
# #         door_controller=door_ctrl,
# #         alarm_controller=alarm_ctrl
# #     )
# #     pin_sync_service = PinSyncService(uart_handler=uart, pin_queue=pin_sync_queue)

# #     # ================= 6. MINI-SERVER (Nhận lệnh từ Web & Live Stream) =================
# #     async def handle_unlock(request):
# #         log_app("info", "Nhận lệnh MỞ CỬA TỪ XA từ Backend!")
# #         try:
# #             await uart.send("CMD_UNLOCK_DOOR\n") # Gửi xuống STM32
# #         except Exception:
# #             pass
# #         return web.json_response({"success": True})

# #     async def handle_enroll(request):
# #         data = await request.json()
# #         name = data.get("name", "Unknown")
# #         resident_id = data.get("id")
# #         log_app("info", f"Nhận lệnh THÊM CƯ DÂN. Đang chụp cho: {name}")

# #         asyncio.create_task(enroll(name, resident_id, num_samples=5))
# #         return web.json_response({"success": True})

# #     async def handle_status(request):
# #         return web.json_response({"door_locked": True, "alarm_active": alarm_ctrl.is_active, "camera_active": shared_camera.is_active})

# #     # --- API PHÁT VIDEO LIVE STREAM ---
# #     async def handle_video_feed(request):
# #         """Phát liên tục các khung hình cho Web Dashboard mà không gọi AI."""
# #         response = web.StreamResponse(
# #             status=200,
# #             reason='OK',
# #             headers={
# #                 'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
# #                 'Cache-Control': 'no-cache',
# #                 'Access-Control-Allow-Origin': '*' # Cho phép Web truy cập chéo
# #             }
# #         )
# #         await response.prepare(request)

# #         try:
# #             while True:
# #                 # Lấy frame trực tiếp từ camera đang mở 24/24
# #                 frame = await shared_camera.capture_frame()
# #                 if frame is not None:
# #                     # Chuyển RGB (chuẩn của camera_manager) -> BGR (chuẩn của OpenCV imencode)
# #                     bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

# #                     # Nén ảnh JPEG (chất lượng 60% để stream mượt qua mạng WiFi/4G)
# #                     ret, buffer = cv2.imencode('.jpg', bgr_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
# #                     if ret:
# #                         frame_data = buffer.tobytes()
# #                         content = (
# #                             b'--frame\r\n'
# #                             b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n'
# #                         )
# #                         await response.write(content)

# #                 # Cấp lại quyền điều khiển cho CPU một chút (nghỉ 30ms -> ~30fps)
# #                 await asyncio.sleep(0.03)
# #         except Exception as e:
# #             log_app("debug", f"Video stream disconnected: {e}")
# #             pass

# #         return response
# #     # ----------------------------------------

# #     # Khởi động Web Server cổng 5000
# #     app = web.Application()

# #     import aiohttp_cors
# #     cors = aiohttp_cors.setup(app, defaults={
# #         "*": aiohttp_cors.ResourceOptions(
# #             allow_credentials=True,
# #             expose_headers="*",
# #             allow_headers="*",
# #         )
# #     })

# #     cors.add(app.router.add_post('/door/unlock', handle_unlock))
# #     cors.add(app.router.add_post('/camera/enroll', handle_enroll))
# #     cors.add(app.router.add_get('/status', handle_status))
# #     cors.add(app.router.add_get('/video_feed', handle_video_feed))

# #     runner = web.AppRunner(app)
# #     await runner.setup()
# #     site = web.TCPSite(runner, '0.0.0.0', 5000)
# #     await site.start()
# #     log_app("info", "Pi Local API Server started on port 5000")

# #     # ==============================================================================

# #     # 7. Gói tất cả vào các Background Tasks
# #     tasks = [
# #         asyncio.create_task(uart.listen_loop(uart_rx_queue), name="uart_rx"),
# #         asyncio.create_task(event_dispatcher.dispatch_loop(), name="event_dispatch"),
# #         asyncio.create_task(pin_sync_service.run(), name="pin_sync"),
# #         asyncio.create_task(poll_pin_changes(pin_sync_queue), name="pin_poll"),
# #         asyncio.create_task(heartbeat_loop(), name="api_heartbeat"),
# #         asyncio.create_task(state_machine.run(), name="state_machine"),
# #         asyncio.create_task(auto_upload_pending_loop(), name="auto_upload_pending")
# #     ]

# #     log_app("info", "All services running. Entering main loop.")

# #     # 8. Theo dõi các task. Nếu có task nào chết bất thường, log lại và thoát
# #     try:
# #         done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
# #         for task in done:
# #             if task.exception():
# #                 log_app("error", f"Task {task.get_name()} crashed: {task.exception()}")
# #     except asyncio.CancelledError:
# #         log_app("info", "System shutting down...")
# #     finally:
# #         # Graceful shutdown (Tắt hệ thống gọn gàng, dọn dẹp bộ nhớ)
# #         for task in tasks:
# #             task.cancel()
# #         uart.close()

# #         # Nhớ tắt camera dùng chung đi khi tắt hệ thống
# #         await shared_camera.camera_off()

# #         log_event(EventType.SYSTEM_STOP)
# #         log_app("info", "System stopped gracefully.")


# # if __name__ == "__main__":
# #     try:
# #         # Chạy Event Loop chính của ứng dụng
# #         asyncio.run(async_main())
# #     except KeyboardInterrupt:
# #         print("\n[INFO] Bị ngắt bởi người dùng (Ctrl+C). Đang tắt hệ thống...")


# """
# pi/main.py

# Mục đích: Entry point của hệ thống Smart Door trên Raspberry Pi 4.
#           Khởi chạy aiohttp mini-server (port 5000) để nhận lệnh từ
#           Backend FastAPI, đồng thời chạy tất cả background tasks.

# VẤN ĐỀ CŨ:
#   - Thiếu endpoints /door/lock, /alarm/stop, /pin/update mà Backend gọi
#     → 404 khi user nhấn "Khóa cửa", "Dừng alarm", "Đổi PIN".

# GIẢI PHÁP:
#   - Thêm đủ các route mà Backend device.py và pin_management.py cần:
#       POST /door/unlock   → gửi CMD_UNLOCK_DOOR qua UART
#       POST /door/lock     → gửi CMD_LOCK_DOOR qua UART
#       POST /alarm/stop    → gửi CMD_STOP_ALARM qua UART
#       POST /pin/update    → nhận pin_hash mới, sync xuống STM32 qua UART
#       POST /camera/enroll → chụp ảnh đăng ký khuôn mặt
#       GET  /status        → trả về trạng thái hệ thống
#       GET  /video_feed    → MJPEG live stream cho Dashboard

# KIẾN TRÚC:
#   Backend (192.168.137.1:8000) → HTTP → Pi aiohttp (192.168.137.2:5000)
#                                         → UART → STM32
# """

# from __future__ import annotations

# import asyncio
# import sys
# from pathlib import Path

# from aiohttp import web
# import aiohttp_cors
# import cv2

# sys.path.insert(0, str(Path(__file__).resolve().parent))

# from recognition.enroll_face import enroll
# from config.settings import settings
# from logging_module.event_logger import log_app, log_event, EventType

# from communication.uart_handler import UartHandler
# from communication.api_client import heartbeat_loop
# from communication.cloud_uploader import upload_pending
# from communication.pin_sync_service import PinSyncService, poll_pin_changes

# from control.event_handler import EventQueues, EventHandler
# from control.door_controller import DoorController
# from control.alarm_controller import AlarmController
# from control.state_machine import StateMachine

# from vision.camera_manager import CameraManager


# # ── Offline sync loop ─────────────────────────────────────────────────────────

# async def auto_upload_pending_loop():
#     """Cứ 15 giây upload lại ảnh bị kẹt lúc mất mạng."""
#     while True:
#         try:
#             await upload_pending()
#         except Exception as e:
#             log_app('error', f'upload_pending loop error: {e}')
#         await asyncio.sleep(15)


# # ── Main ──────────────────────────────────────────────────────────────────────

# async def async_main() -> None:
#     settings.ensure_dirs()
#     log_app('info', 'System starting...')
#     log_event(EventType.SYSTEM_START)

#     # Upload lại ảnh kẹt từ lần trước
#     await upload_pending()

#     # ── Khởi tạo tài nguyên dùng chung ───────────────────────────────────────
#     shared_camera = CameraManager()
#     await shared_camera.camera_on()

#     uart_rx_queue:  asyncio.Queue[str] = asyncio.Queue()
#     pin_sync_queue: asyncio.Queue[str] = asyncio.Queue()
#     event_queues = EventQueues()

#     uart = UartHandler()
#     try:
#         uart.connect()
#     except Exception as e:
#         log_app('error', f'UART connect failed: {e}. Exiting.')
#         sys.exit(1)

#     event_dispatcher = EventHandler(uart_queue=uart_rx_queue, event_queues=event_queues)

#     door_ctrl  = DoorController(uart_handler=uart)
#     door_ctrl._camera = shared_camera   # inject camera dùng chung

#     alarm_ctrl = AlarmController(uart_handler=uart)

#     state_machine = StateMachine(
#         event_queues=event_queues,
#         door_controller=door_ctrl,
#         alarm_controller=alarm_ctrl,
#     )
#     pin_sync_service = PinSyncService(uart_handler=uart, pin_queue=pin_sync_queue)

#     # ── aiohttp Handlers ──────────────────────────────────────────────────────

#     async def handle_unlock(request):
#         log_app('info', 'Lệnh MỞ CỬA từ Backend')
#         try:
#             await uart.send('CMD_UNLOCK_DOOR\n')
#         except Exception as e:
#             log_app('error', f'UART send unlock error: {e}')
#         return web.json_response({'success': True})

#     async def handle_lock(request):
#         log_app('info', 'Lệnh KHÓA CỬA từ Backend')
#         try:
#             await uart.send('CMD_LOCK_DOOR\n')
#         except Exception as e:
#             log_app('error', f'UART send lock error: {e}')
#         return web.json_response({'success': True})

#     async def handle_stop_alarm(request):
#         log_app('info', 'Lệnh DỪNG ALARM từ Backend')
#         try:
#             await uart.send('CMD_STOP_ALARM\n')
#             await alarm_ctrl.stop()
#         except Exception as e:
#             log_app('error', f'UART send stop_alarm error: {e}')
#         return web.json_response({'success': True})

#     async def handle_test_buzzer(request):
#         log_app('info', 'Lệnh TEST BUZZER từ Backend')
#         try:
#             await uart.send('CMD_TEST_BUZZER\n')
#         except Exception as e:
#             log_app('error', f'UART send test_buzzer error: {e}')
#         return web.json_response({'success': True})

#     async def handle_update_pin(request):
#         """
#         Nhận pin_hash từ Backend, gửi xuống STM32 qua UART.
#         Backend gửi: {"pin_hash": "<bcrypt_hash>"}
#         Pi chuyển thành lệnh UART: SET_PIN_HASH:<hash>
#         """
#         try:
#             data     = await request.json()
#             pin_hash = data.get('pin_hash', '')
#             if not pin_hash:
#                 return web.json_response({'success': False, 'error': 'Missing pin_hash'}, status=400)
#             log_app('info', 'Nhận PIN hash mới từ Backend, đang sync xuống STM32...')
#             await uart.send(f'SET_PIN_HASH:{pin_hash}\n')
#             return web.json_response({'success': True})
#         except Exception as e:
#             log_app('error', f'handle_update_pin error: {e}')
#             return web.json_response({'success': False, 'error': str(e)}, status=500)

#     async def handle_enroll(request):
#         data        = await request.json()
#         name        = data.get('name', 'Unknown')
#         resident_id = data.get('id')
#         log_app('info', f'Lệnh THÊM CƯ DÂN: {name}')
#         asyncio.create_task(enroll(name, resident_id, num_samples=5))
#         return web.json_response({'success': True})

#     async def handle_status(request):
#         return web.json_response({
#             'door_locked':   True,
#             'alarm_active':  alarm_ctrl.is_active,
#             'camera_active': shared_camera.is_active,
#         })

#     async def handle_video_feed(request):
#         """MJPEG stream — trực tiếp từ camera, không qua AI."""
#         response = web.StreamResponse(
#             status=200,
#             reason='OK',
#             headers={
#                 'Content-Type':  'multipart/x-mixed-replace; boundary=frame',
#                 'Cache-Control': 'no-cache',
#                 'Access-Control-Allow-Origin': '*',
#             },
#         )
#         await response.prepare(request)
#         try:
#             while True:
#                 frame = await shared_camera.capture_frame()
#                 if frame is not None:
#                     bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
#                     ret, buffer = cv2.imencode(
#                         '.jpg', bgr_frame,
#                         [int(cv2.IMWRITE_JPEG_QUALITY), 60],
#                     )
#                     if ret:
#                         content = (
#                             b'--frame\r\n'
#                             b'Content-Type: image/jpeg\r\n\r\n' +
#                             buffer.tobytes() + b'\r\n'
#                         )
#                         await response.write(content)
#                 await asyncio.sleep(0.033)   # ~30 fps
#         except Exception as e:
#             log_app('debug', f'Video stream disconnected: {e}')
#         return response

#     # ── aiohttp App + CORS ────────────────────────────────────────────────────
#     app  = web.Application()
#     cors = aiohttp_cors.setup(app, defaults={
#         '*': aiohttp_cors.ResourceOptions(
#             allow_credentials=True,
#             expose_headers='*',
#             allow_headers='*',
#         )
#     })

#     # Đầy đủ các route mà Backend device.py và pin_management.py cần
#     cors.add(app.router.add_post('/door/unlock',    handle_unlock))
#     cors.add(app.router.add_post('/door/lock',      handle_lock))
#     cors.add(app.router.add_post('/alarm/stop',     handle_stop_alarm))
#     cors.add(app.router.add_post('/buzzer/test',    handle_test_buzzer))
#     cors.add(app.router.add_post('/pin/update',     handle_update_pin))
#     cors.add(app.router.add_post('/camera/enroll',  handle_enroll))
#     cors.add(app.router.add_get('/status',          handle_status))
#     cors.add(app.router.add_get('/video_feed',      handle_video_feed))

#     runner = web.AppRunner(app)
#     await runner.setup()
#     site = web.TCPSite(runner, '0.0.0.0', 5000)
#     await site.start()
#     log_app('info', 'Pi Local API Server started on :5000')

#     # ── Background Tasks ──────────────────────────────────────────────────────
#     tasks = [
#         asyncio.create_task(uart.listen_loop(uart_rx_queue),         name='uart_rx'),
#         asyncio.create_task(event_dispatcher.dispatch_loop(),         name='event_dispatch'),
#         asyncio.create_task(pin_sync_service.run(),                   name='pin_sync'),
#         asyncio.create_task(poll_pin_changes(pin_sync_queue),         name='pin_poll'),
#         asyncio.create_task(heartbeat_loop(),                         name='api_heartbeat'),
#         asyncio.create_task(state_machine.run(),                      name='state_machine'),
#         asyncio.create_task(auto_upload_pending_loop(),               name='auto_upload_pending'),
#     ]

#     log_app('info', 'All services running.')

#     try:
#         done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
#         for task in done:
#             if task.exception():
#                 log_app('error', f'Task {task.get_name()} crashed: {task.exception()}')
#     except asyncio.CancelledError:
#         log_app('info', 'System shutting down...')
#     finally:
#         for task in tasks:
#             task.cancel()
#         uart.close()
#         await shared_camera.camera_off()
#         log_event(EventType.SYSTEM_STOP)
#         log_app('info', 'System stopped.')


# if __name__ == '__main__':
#     try:
#         asyncio.run(async_main())
#     except KeyboardInterrupt:
#         print('\n[INFO] Interrupted by user (Ctrl+C). Shutting down...')

"""
pi/main.py

Mục đích: Entry point của hệ thống Smart Door trên Raspberry Pi 4.
    - Khởi chạy aiohttp mini-server (port 5000) nhận lệnh từ Backend.
    - Tích hợp bộ não PresenceDetector lọc người đi ngang qua.
    - Quản lý các Background Tasks (UART, Sync PIN, Heartbeat).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from aiohttp import web
import aiohttp_cors
import cv2

# Đảm bảo import path đúng
sys.path.insert(0, str(Path(__file__).resolve().parent))

from recognition.enroll_face import enroll
from config.settings import settings
from logging_module.event_logger import log_app, log_event, EventType

from communication.uart_handler import UartHandler
from communication.api_client import heartbeat_loop
from communication.cloud_uploader import upload_pending
from communication.pin_sync_service import PinSyncService, poll_pin_changes

from control.event_handler import EventQueues, EventHandler
from control.door_controller import DoorController
from control.alarm_controller import AlarmController
from control.state_machine import StateMachine
from control.presence_detector import PresenceDetector  # <-- Import bộ não mới

from vision.camera_manager import CameraManager


# ── Offline sync loop ─────────────────────────────────────────────────────────

async def auto_upload_pending_loop():
    """Cứ 15 giây upload lại ảnh bị kẹt lúc mất mạng."""
    while True:
        try:
            await upload_pending()
        except Exception as e:
            log_app('error', f'upload_pending loop error: {e}')
        await asyncio.sleep(15)


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def async_main() -> None:
    settings.ensure_dirs()
    log_app('info', 'System starting...')
    log_event(EventType.SYSTEM_START)

    # 1. Khởi tạo tài nguyên phần cứng
    shared_camera = CameraManager()
    await shared_camera.camera_on()

    uart = UartHandler()
    try:
        uart.connect()
    except Exception as e:
        log_app('error', f'UART connect failed: {e}. Exiting.')
        sys.exit(1)

    # 2. Khởi tạo các bộ điều khiển (Controllers)
    door_ctrl  = DoorController(uart_handler=uart)
    alarm_ctrl = AlarmController(uart_handler=uart)

    # 3. Định nghĩa các hành động cho bộ não PresenceDetector
    async def on_face_ok(result):
        """Hàm gọi khi AI nhận diện đúng cư dân."""
        await door_ctrl.handle_detection_result(result)

    async def on_face_fail(result):
        """Hàm gọi khi AI thấy người lạ."""
        await uart.send("CMD_WARNING_BEEP\n") # Kêu tít tít cảnh báo nhẹ
        await door_ctrl.handle_detection_result(result)

    async def on_panic_alarm():
        """Hàm gọi khi sai quá 5 lần."""
        log_app("warning", "Quét sai quá nhiều lần! Kích hoạt báo động.")
        await alarm_ctrl.start()

    # 4. Khởi tạo Bộ Não PresenceDetector
    detector = PresenceDetector(
        camera=shared_camera,
        on_recognized=on_face_ok,   # Khớp với PresenceDetector.__init__
        on_unknown=on_face_fail,     # Khớp với PresenceDetector.__init__
        on_alarm=on_panic_alarm      # Khớp với PresenceDetector.__init__
    )

    # 5. Khởi tạo luồng xử lý sự kiện
    uart_rx_queue:  asyncio.Queue[str] = asyncio.Queue()
    pin_sync_queue: asyncio.Queue[str] = asyncio.Queue()
    event_queues = EventQueues()

    event_dispatcher = EventHandler(uart_queue=uart_rx_queue, event_queues=event_queues)

    # StateMachine nhận lệnh PIR và đẩy qua Detector
    state_machine = StateMachine(
        event_queues=event_queues,
        door_controller=door_ctrl,
        presence_detector=detector  # <-- Truyền detector vào đây
    )

    pin_sync_service = PinSyncService(uart_handler=uart, pin_queue=pin_sync_queue)

    # ── aiohttp Handlers (Nhận lệnh từ Web qua Backend) ───────────────────────

    async def handle_unlock(request):
        await door_ctrl.unlock()
        return web.json_response({'success': True})

    async def handle_lock(request):
        await door_ctrl.lock()
        return web.json_response({'success': True})

    async def handle_stop_alarm(request):
        await alarm_ctrl.stop()
        return web.json_response({'success': True})

    async def handle_test_buzzer(request):
        log_app('info', 'Lệnh TEST BUZZER từ Web')
        await uart.send('CMD_TEST_BUZZER\n')
        return web.json_response({'success': True})

    async def handle_update_pin(request):
        try:
            data = await request.json()
            pin_hash = data.get('pin_hash', '')
            await uart.send(f'SET_PIN_HASH:{pin_hash}\n')
            return web.json_response({'success': True})
        except Exception as e:
            return web.json_response({'success': False, 'error': str(e)}, status=500)

    async def handle_enroll(request):
        data = await request.json()
        asyncio.create_task(enroll(data.get('name'), data.get('id'), num_samples=5))
        return web.json_response({'success': True})

    async def handle_status(request):
        return web.json_response({
            'door_locked':   True,
            'alarm_active':  alarm_ctrl.is_active,
            'camera_active': shared_camera.is_active,
        })

    async def handle_video_feed(request):
        """MJPEG stream trực tiếp cho Web."""
        response = web.StreamResponse(
            status=200, headers={
                'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
                'Cache-Control': 'no-cache',
                'Access-Control-Allow-Origin': '*',
            }
        )
        await response.prepare(request)
        try:
            while True:
                frame = await shared_camera.capture_frame()
                if frame is not None:
                    ret, buffer = cv2.imencode('.jpg', frame[:,:,::-1], [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                    if ret:
                        await response.write(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
                await asyncio.sleep(0.033)
        except: pass
        return response

    # ── App Server Setup ──────────────────────────────────────────────────────
    app = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        '*': aiohttp_cors.ResourceOptions(allow_credentials=True, expose_headers='*', allow_headers='*')
    })
    cors.add(app.router.add_post('/door/unlock',   handle_unlock))
    cors.add(app.router.add_post('/door/lock',     handle_lock))
    cors.add(app.router.add_post('/alarm/stop',    handle_stop_alarm))
    cors.add(app.router.add_post('/buzzer/test',   handle_test_buzzer))
    cors.add(app.router.add_post('/pin/update',    handle_update_pin))
    cors.add(app.router.add_post('/camera/enroll', handle_enroll))
    cors.add(app.router.add_get('/status',         handle_status))
    cors.add(app.router.add_get('/video_feed',     handle_video_feed))

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', 5000).start()
    log_app('info', 'Pi API Server ready on port 5000')

    # ── Background Tasks Execution ────────────────────────────────────────────
    tasks = [
        asyncio.create_task(uart.listen_loop(uart_rx_queue),    name='uart_rx'),
        asyncio.create_task(event_dispatcher.dispatch_loop(),    name='event_dispatch'),
        asyncio.create_task(pin_sync_service.run(),              name='pin_sync'),
        asyncio.create_task(poll_pin_changes(pin_sync_queue),    name='pin_poll'),
        asyncio.create_task(heartbeat_loop(),                    name='api_heartbeat'),
        asyncio.create_task(state_machine.run(),                 name='state_machine'),
        asyncio.create_task(auto_upload_pending_loop(),          name='auto_upload_pending'),
    ]

    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            if task.exception():
                log_app('error', f'Task {task.get_name()} crashed: {task.exception()}')
    except asyncio.CancelledError:
        pass
    finally:
        for t in tasks: t.cancel()
        uart.close()
        await shared_camera.camera_off()
        log_app('info', 'System stopped.')

if __name__ == '__main__':
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print('\n[INFO] Stopped by user.')

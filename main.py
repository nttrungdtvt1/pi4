# """
# pi4/main.py — Entry point Smart Door Pi 4

# CHANGES & FIXES:
#   [NEW] TÍCH HỢP TÍNH NĂNG BẮT TAY UART (HANDSHAKE): Kiểm tra kết nối vật lý ngay lúc khởi động.
#   [FIX] Bổ sung `uart_send_fn=uart.send` cho PresenceDetector để gửi lệnh đếm số lần quét xuống LCD STM32.
#   [FIX] Đã chuẩn hóa JSON cho hàm _broadcast_to_backend để tránh lỗi 422.
#   [NEW] Bổ sung API /config/update để nhận ĐỒNG THỜI cấu hình còi và cấu hình cửa từ Web.
#   [FIX] Hàm handle_unlock đọc thêm "reason" từ JSON để ghi log lên Dashboard.
#   [CLEANUP] Đã loại bỏ luồng giả lập auto_trigger_pir do đã có phần cứng thật.
#   [FIX CRITICAL] Thêm cơ chế khóa PIR 60 giây sau khi quét mặt trượt 5 lần để ưu tiên Keypad.
# """
# from __future__ import annotations

# import asyncio
# import sys
# import time
# from pathlib import Path

# from aiohttp import web
# import aiohttp_cors
# import cv2

# # Đảm bảo import path đúng
# sys.path.insert(0, str(Path(__file__).resolve().parent))

# from recognition.enroll_face import enroll
# from config.settings import settings
# from logging_module.event_logger import log_app, log_event, EventType

# from communication.uart_handler import UartHandler
# from communication.api_client import heartbeat_loop, post_access_log
# from communication.cloud_uploader import upload_pending
# from communication.pin_sync_service import PinSyncService, poll_pin_changes
# from communication.pin_from_device_service import PinFromDeviceService

# from control.event_handler import EventQueues, EventHandler
# from control.door_controller import DoorController
# from control.alarm_controller import AlarmController
# from control.state_machine import StateMachine
# from control.presence_detector import PresenceDetector

# from vision.camera_manager import CameraManager

# from services.face_sync_service import (
#     handle_sync_push,
#     handle_delete_push,
#     face_sync_pull_loop,
# )

# # ── Pi → Backend broadcast helper ─────────────────────────────────────────────

# async def _broadcast_to_backend(event_type: str, data: dict) -> None:
#     if event_type == "scan_frame":
#         return

#     from communication.api_client import post_event
#     try:
#         import json
#         msg = data.get("message") or data.get("detail") or data.get("reason") or json.dumps(data)
#         await post_event(event_type, message=str(msg))
#     except Exception as exc:
#         log_app("debug", f"[broadcast] Failed to push '{event_type}': {exc}")


# # ── Upload retry loop ──────────────────────────────────────────────────────────

# async def auto_upload_pending_loop() -> None:
#     while True:
#         try:
#             await upload_pending()
#         except Exception as exc:
#             log_app("error", f"upload_pending loop: {exc}")
#         await asyncio.sleep(15)

# # ── Main ──────────────────────────────────────────────────────────────────────

# async def async_main() -> None:
#     settings.ensure_dirs()

#     svc_dir = Path(__file__).resolve().parent / "services"
#     svc_dir.mkdir(exist_ok=True)
#     (svc_dir / "__init__.py").touch(exist_ok=True)

#     log_app("info", "System starting...")
#     log_event(EventType.SYSTEM_START)

#     # ── Hardware ──────────────────────────────────────────────────────────────
#     shared_camera = CameraManager()
#     # Không bật camera ở đây nữa để ưu tiên chế độ Ngủ đông tiết kiệm pin

#     uart = UartHandler()
#     try:
#         uart.connect()
#     except Exception as exc:
#         log_app("error", f"UART connect failed: {exc}. Exiting.")
#         sys.exit(1)

#     # ── BẮT TAY UART (HANDSHAKE) ───────────────────────────────
#     uart_rx_queue:         asyncio.Queue[str] = asyncio.Queue()
#     pin_from_device_queue: asyncio.Queue[str] = asyncio.Queue()

#     listen_task = asyncio.create_task(uart.listen_loop(uart_rx_queue, pin_from_device_queue), name="uart_rx")

#     log_app("info", "Đang kiểm tra kết nối UART với STM32 (Handshake)...")
#     await uart.send("CMD_PING\n")

#     handshake_ok = False
#     start_time = time.monotonic()

#     while time.monotonic() - start_time < 3.0:
#         try:
#             msg = await asyncio.wait_for(uart_rx_queue.get(), timeout=0.5)
#             if "ACK_PING" in msg:
#                 handshake_ok = True
#                 break
#             else:
#                 await uart_rx_queue.put(msg)
#         except asyncio.TimeoutError:
#             continue
#         except Exception as e:
#             log_app("error", f"Lỗi đọc Queue lúc Handshake: {e}")
#             break

#     if handshake_ok:
#         log_app("info", "✅ HANDSHAKE OK: Đã kết nối UART thành công với STM32!")
#     else:
#         log_app("error", "❌ HANDSHAKE FAILED: Không thấy STM32 trả lời! Đang dừng hệ thống...")
#         log_app("error", "👉 BẠN HÃY KIỂM TRA LẠI: 1. Đã cắm chéo dây TX-RX chưa? 2. Đã cắm dây GND chung chưa?")
#         listen_task.cancel()
#         uart.close()
#         await shared_camera.camera_off()
#         sys.exit(1)

#     # ── Controllers ───────────────────────────────
#     door_ctrl  = DoorController(uart_handler=uart)
#     alarm_ctrl = AlarmController(uart_handler=uart)

#     async def on_face_ok(result):
#         await door_ctrl.handle_detection_result(result)
#         try:
#             if result.image_path:
#                 from communication.cloud_uploader import upload
#                 image_url = await upload(Path(result.image_path))
#                 await post_access_log(result.name, "face", True, image_url or "")
#         except Exception as exc:
#             log_app("warning", f"on_face_ok post_log: {exc}")

#     async def on_face_fail(result):
#         from config.constants import CMD_WARNING_BEEP
#         await uart.send(f"{CMD_WARNING_BEEP}\n")
#         await door_ctrl.handle_detection_result(result)
#         try:
#             if result.image_path:
#                 from communication.cloud_uploader import upload
#                 image_url = await upload(Path(result.image_path))
#                 await post_access_log(None, "face", False, image_url or "")
#         except Exception as exc:
#             log_app("warning", f"on_face_fail post_log: {exc}")

#     async def on_panic_alarm():
#         log_app("warning", "Too many failed scans → alarm & enable keypad")
        
#         # ✅ ĐÃ FIX: Khóa mạch cảm biến PIR 60 giây!
#         # Việc này đảm bảo quá trình nhập mã PIN không bị làm phiền bởi những cử động tay của bạn.
#         state_machine._pir_lock_until = asyncio.get_event_loop().time() + 60.0
#         log_app("info", "Đã khóa cảm biến PIR 60 giây để ưu tiên thao tác nhập mã PIN.")
        
#         await alarm_ctrl.start()

#     detector = PresenceDetector(
#         camera=shared_camera,
#         on_recognized=on_face_ok,
#         on_unknown=on_face_fail,
#         on_alarm=on_panic_alarm,
#         broadcast_fn=_broadcast_to_backend,
#         uart_send_fn=uart.send,
#     )

#     # ── Queues & Services ─────────────────────────────────────────────────────
#     pin_sync_queue: asyncio.Queue[str] = asyncio.Queue()
#     event_queues = EventQueues()

#     event_dispatcher = EventHandler(
#         uart_queue=uart_rx_queue, event_queues=event_queues
#     )
    
#     # Khởi tạo StateMachine, biến này sẽ được gọi ngược ở hàm on_panic_alarm bên trên
#     state_machine = StateMachine(
#         event_queues=event_queues,
#         door_controller=door_ctrl,
#         presence_detector=detector,
#     )
    
#     pin_sync_service = PinSyncService(uart_handler=uart, pin_queue=pin_sync_queue)
#     pin_device_svc   = PinFromDeviceService(pin_from_device_queue=pin_from_device_queue)

#     # ── aiohttp handlers ──────────────────────────────────────────────────────

#     async def handle_unlock(request):
#         reason = "Mở khóa từ xa"
#         try:
#             if request.can_read_body:
#                 data = await request.json()
#                 reason = data.get("reason", reason)
#         except Exception:
#             pass

#         await door_ctrl.unlock()
#         log_app("info", f"Mở cửa thủ công từ Web. Lý do: {reason}")
        
#         try:
#             await post_access_log(name=f"Admin (Lý do: {reason})", method="remote", success=True, image_url="")
#         except Exception as e:
#             log_app("warning", f"Lỗi ghi log mở cửa từ xa: {e}")

#         return web.json_response({"success": True})

#     async def handle_lock(request):
#         await door_ctrl.lock()
#         return web.json_response({"success": True})

#     async def handle_stop_alarm(request):
#         await alarm_ctrl.stop()
#         return web.json_response({"success": True})

#     async def handle_test_buzzer(request):
#         from config.constants import CMD_TEST_BUZZER
#         await uart.send(f"{CMD_TEST_BUZZER}\n")
#         return web.json_response({"success": True})

#     async def handle_update_pin(request):
#         try:
#             data = await request.json()
#             pin  = data.get("pin", "")
#             if not pin or len(pin) < 4:
#                 return web.json_response({"success": False, "error": "Invalid PIN"}, status=400)
#             import hashlib, hmac as _hmac
#             secret   = settings.hmac_secret_key.encode("utf-8")
#             hmac_hex = _hmac.new(secret, pin.encode("utf-8"), hashlib.sha256).hexdigest()
#             await uart.send(f"SET_PIN_HASH:{hmac_hex}\n")
#             return web.json_response({"success": True})
#         except Exception as exc:
#             return web.json_response({"success": False, "error": str(exc)}, status=500)

#     async def handle_update_config(request):
#         try:
#             data = await request.json()
            
#             if "alarm_duration" in data:
#                 alarm_duration_sec = int(data["alarm_duration"])
#                 alarm_ctrl.duration = alarm_duration_sec
#                 log_app("info", f"Cập nhật cấu hình: Còi hú trong {alarm_duration_sec} giây")
                
#             if "auto_lock_duration" in data:
#                 lock_sec_str = str(data["auto_lock_duration"]).lower()
#                 if "không" in lock_sec_str or "never" in lock_sec_str:
#                     lock_sec = 0
#                 else:
#                     lock_sec = int(''.join(filter(str.isdigit, lock_sec_str)))
                
#                 success = await uart.send(f"SET_TIMEOUT:{lock_sec}\n", expect_ack="ACK_TIMEOUT")
#                 if success:
#                     log_app("info", f"Cấu hình cửa: Tự đóng sau {lock_sec} giây (Đã lưu STM32)")
#                 else:
#                     log_app("warning", "Gửi cấu hình cửa thất bại (Không nhận được ACK từ STM32)")
            
#             return web.json_response({"success": True})
#         except Exception as exc:
#             return web.json_response({"success": False, "error": str(exc)}, status=400)

#     async def handle_enroll(request):
#         data = await request.json()
#         asyncio.create_task(enroll(data.get("name"), data.get("id"), num_samples=5))
#         return web.json_response({"success": True})

#     async def handle_sync_faces(request):
#         api_key = request.headers.get("X-Api-Key", "")
#         if api_key != settings.api_key:
#             return web.json_response({"success": False, "error": "Unauthorized"}, status=403)
#         try:
#             data    = await request.json()
#             log_app(
#                 "info",
#                 f"[sync-faces] Push: resident_id={data.get('resident_id')} "
#                 f"name='{data.get('name')}'",
#             )
#             result = await handle_sync_push(data)
#             return web.json_response(result, status=200 if result["success"] else 500)
#         except Exception as exc:
#             log_app("error", f"handle_sync_faces: {exc}")
#             return web.json_response({"success": False, "error": str(exc)}, status=500)

#     async def handle_delete_face(request):
#         api_key = request.headers.get("X-Api-Key", "")
#         if api_key != settings.api_key:
#             return web.json_response({"success": False, "error": "Unauthorized"}, status=403)
#         try:
#             data   = await request.json()
#             result = await handle_delete_push(data)
#             return web.json_response(result)
#         except Exception as exc:
#             return web.json_response({"success": False, "error": str(exc)}, status=500)

#     async def handle_status(request):
#         return web.json_response({
#             "door_locked":   True,
#             "alarm_active":  alarm_ctrl.is_active,
#             "camera_active": shared_camera.is_active,
#         })

#     async def handle_video_feed(request):
#         response = web.StreamResponse(
#             status=200,
#             headers={
#                 "Content-Type":  "multipart/x-mixed-replace; boundary=frame",
#                 "Cache-Control": "no-cache",
#                 "Access-Control-Allow-Origin": "*",
#             },
#         )
#         await response.prepare(request)
#         try:
#             while True:
#                 frame = await shared_camera.capture_frame()
#                 if frame is not None:
#                     ret, buf = cv2.imencode(
#                         ".jpg", frame[:, :, ::-1],
#                         [int(cv2.IMWRITE_JPEG_QUALITY), 60],
#                     )
#                     if ret:
#                         await response.write(
#                             b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
#                             + buf.tobytes()
#                             + b"\r\n"
#                         )
#                 await asyncio.sleep(0.033)
#         except Exception:
#             pass
#         return response

#     # ── App server ────────────────────────────────────────────────────────────
#     app  = web.Application()
#     cors = aiohttp_cors.setup(app, defaults={
#         "*": aiohttp_cors.ResourceOptions(
#             allow_credentials=True, expose_headers="*", allow_headers="*"
#         )
#     })

#     cors.add(app.router.add_post("/door/unlock",    handle_unlock))
#     cors.add(app.router.add_post("/door/lock",      handle_lock))
#     cors.add(app.router.add_post("/alarm/stop",     handle_stop_alarm))
#     cors.add(app.router.add_post("/buzzer/test",    handle_test_buzzer))
#     cors.add(app.router.add_post("/pin/update",     handle_update_pin))
#     cors.add(app.router.add_post("/config/update",  handle_update_config))
#     cors.add(app.router.add_post("/camera/enroll",  handle_enroll))
#     cors.add(app.router.add_post("/sync-faces",     handle_sync_faces))
#     cors.add(app.router.add_post("/delete-face",    handle_delete_face))
#     cors.add(app.router.add_get( "/status",         handle_status))
#     cors.add(app.router.add_get( "/video_feed",     handle_video_feed))

#     runner = web.AppRunner(app)
#     await runner.setup()
#     await web.TCPSite(runner, "0.0.0.0", 5000).start()
#     log_app("info", "Pi API Server ready on :5000")

#     # ── Background tasks ───────────────────────────────────────────────────────
#     tasks = [
#         listen_task, 
#         asyncio.create_task(event_dispatcher.dispatch_loop(),  name="event_dispatch"),
#         asyncio.create_task(pin_sync_service.run(),            name="pin_sync_w2d"),
#         asyncio.create_task(pin_device_svc.run(),              name="pin_sync_d2w"),
#         asyncio.create_task(poll_pin_changes(pin_sync_queue),  name="pin_poll"),
#         asyncio.create_task(heartbeat_loop(),                  name="heartbeat"),
#         asyncio.create_task(state_machine.run(),               name="state_machine"),
#         asyncio.create_task(auto_upload_pending_loop(),        name="upload_pending"),
#         asyncio.create_task(face_sync_pull_loop(),             name="face_sync_pull"),
#     ]

#     try:
#         done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
#         for task in done:
#             if exc := task.exception():
#                 log_app("error", f"Task '{task.get_name()}' crashed: {exc}")
#     except asyncio.CancelledError:
#         pass
#     finally:
#         for t in tasks:
#             t.cancel()
#         uart.close()
#         await shared_camera.camera_off()
#         log_app("info", "System stopped.")

# if __name__ == "__main__":
#     try:
#         asyncio.run(async_main())
#     except KeyboardInterrupt:
#         print("\n[INFO] Stopped by user.")


"""
pi4/main.py — Entry point Smart Door Pi 4

CHANGES & FIXES:
  [NEW] TÍCH HỢP TÍNH NĂNG BẮT TAY UART (HANDSHAKE): Kiểm tra kết nối vật lý ngay lúc khởi động.
  [FIX] Bổ sung `uart_send_fn=uart.send` cho PresenceDetector để gửi lệnh đếm số lần quét xuống LCD STM32.
  [FIX] Hàm handle_unlock đọc thêm "reason" từ JSON để ghi log lên Dashboard.
  [CLEANUP] Đã loại bỏ luồng giả lập auto_trigger_pir do đã có phần cứng thật.
  [FIX CRITICAL] Thêm cơ chế khóa PIR 60 giây sau khi quét mặt trượt 5 lần để ưu tiên Keypad.
  [FIX UI] Loại bỏ việc bọc JSON thành chuỗi "message" để Frontend đọc được tên chủ nhà.
"""
from __future__ import annotations

import asyncio
import sys
import time
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
from communication.api_client import heartbeat_loop, post_access_log
from communication.cloud_uploader import upload_pending
from communication.pin_sync_service import PinSyncService, poll_pin_changes
from communication.pin_from_device_service import PinFromDeviceService

from control.event_handler import EventQueues, EventHandler
from control.door_controller import DoorController
from control.alarm_controller import AlarmController
from control.state_machine import StateMachine
from control.presence_detector import PresenceDetector

from vision.camera_manager import CameraManager

from services.face_sync_service import (
    handle_sync_push,
    handle_delete_push,
    face_sync_pull_loop,
)

# ── Pi → Backend broadcast helper ─────────────────────────────────────────────

async def _broadcast_to_backend(event_type: str, data: dict) -> None:
    if event_type == "scan_frame":
        return

    from communication.api_client import post_event
    try:
        # ✅ ĐÃ SỬA: KHÔNG BỌC VÀO CHUỖI "message" NỮA, GỬI NGUYÊN CỤC DATA CHUẨN JSON SANG!
        await post_event(event_type, **data)
    except Exception as exc:
        log_app("debug", f"[broadcast] Failed to push '{event_type}': {exc}")


# ── Upload retry loop ──────────────────────────────────────────────────────────

async def auto_upload_pending_loop() -> None:
    while True:
        try:
            await upload_pending()
        except Exception as exc:
            log_app("error", f"upload_pending loop: {exc}")
        await asyncio.sleep(15)

# ── Main ──────────────────────────────────────────────────────────────────────

async def async_main() -> None:
    settings.ensure_dirs()

    svc_dir = Path(__file__).resolve().parent / "services"
    svc_dir.mkdir(exist_ok=True)
    (svc_dir / "__init__.py").touch(exist_ok=True)

    log_app("info", "System starting...")
    log_event(EventType.SYSTEM_START)

    # ── Hardware ──────────────────────────────────────────────────────────────
    shared_camera = CameraManager()
    # Không bật camera ở đây nữa để ưu tiên chế độ Ngủ đông tiết kiệm pin

    uart = UartHandler()
    try:
        uart.connect()
    except Exception as exc:
        log_app("error", f"UART connect failed: {exc}. Exiting.")
        sys.exit(1)

    # ── BẮT TAY UART (HANDSHAKE) ───────────────────────────────
    uart_rx_queue:         asyncio.Queue[str] = asyncio.Queue()
    pin_from_device_queue: asyncio.Queue[str] = asyncio.Queue()

    listen_task = asyncio.create_task(uart.listen_loop(uart_rx_queue, pin_from_device_queue), name="uart_rx")

    log_app("info", "Đang kiểm tra kết nối UART với STM32 (Handshake)...")
    await uart.send("CMD_PING\n")

    handshake_ok = False
    start_time = time.monotonic()

    while time.monotonic() - start_time < 3.0:
        try:
            msg = await asyncio.wait_for(uart_rx_queue.get(), timeout=0.5)
            if "ACK_PING" in msg:
                handshake_ok = True
                break
            else:
                await uart_rx_queue.put(msg)
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            log_app("error", f"Lỗi đọc Queue lúc Handshake: {e}")
            break

    if handshake_ok:
        log_app("info", "✅ HANDSHAKE OK: Đã kết nối UART thành công với STM32!")
    else:
        log_app("error", "❌ HANDSHAKE FAILED: Không thấy STM32 trả lời! Đang dừng hệ thống...")
        log_app("error", "👉 BẠN HÃY KIỂM TRA LẠI: 1. Đã cắm chéo dây TX-RX chưa? 2. Đã cắm dây GND chung chưa?")
        listen_task.cancel()
        uart.close()
        await shared_camera.camera_off()
        sys.exit(1)

    # ── Controllers ───────────────────────────────
    door_ctrl  = DoorController(uart_handler=uart)
    alarm_ctrl = AlarmController(uart_handler=uart)

    async def on_face_ok(result):
        await door_ctrl.handle_detection_result(result)
        try:
            if result.image_path:
                from communication.cloud_uploader import upload
                image_url = await upload(Path(result.image_path))
                await post_access_log(result.name, "face", True, image_url or "")
        except Exception as exc:
            log_app("warning", f"on_face_ok post_log: {exc}")

    async def on_face_fail(result):
        from config.constants import CMD_WARNING_BEEP
        await uart.send(f"{CMD_WARNING_BEEP}\n")
        await door_ctrl.handle_detection_result(result)
        try:
            if result.image_path:
                from communication.cloud_uploader import upload
                image_url = await upload(Path(result.image_path))
                await post_access_log(None, "face", False, image_url or "")
        except Exception as exc:
            log_app("warning", f"on_face_fail post_log: {exc}")

    async def on_panic_alarm():
        log_app("warning", "Too many failed scans → alarm & enable keypad")
        
        # Khóa mạch cảm biến PIR 60 giây!
        state_machine._pir_lock_until = asyncio.get_event_loop().time() + 60.0
        log_app("info", "Đã khóa cảm biến PIR 60 giây để ưu tiên thao tác nhập mã PIN.")
        
        await alarm_ctrl.start()

    detector = PresenceDetector(
        camera=shared_camera,
        on_recognized=on_face_ok,
        on_unknown=on_face_fail,
        on_alarm=on_panic_alarm,
        broadcast_fn=_broadcast_to_backend,
        uart_send_fn=uart.send,
    )

    # ── Queues & Services ─────────────────────────────────────────────────────
    pin_sync_queue: asyncio.Queue[str] = asyncio.Queue()
    event_queues = EventQueues()

    event_dispatcher = EventHandler(
        uart_queue=uart_rx_queue, event_queues=event_queues
    )
    
    # Khởi tạo StateMachine, biến này sẽ được gọi ngược ở hàm on_panic_alarm bên trên
    state_machine = StateMachine(
        event_queues=event_queues,
        door_controller=door_ctrl,
        presence_detector=detector,
    )
    
    pin_sync_service = PinSyncService(uart_handler=uart, pin_queue=pin_sync_queue)
    pin_device_svc   = PinFromDeviceService(pin_from_device_queue=pin_from_device_queue)

    # ── aiohttp handlers ──────────────────────────────────────────────────────

    async def handle_unlock(request):
        reason = "Mở khóa từ xa"
        try:
            if request.can_read_body:
                data = await request.json()
                reason = data.get("reason", reason)
        except Exception:
            pass

        await door_ctrl.unlock()
        log_app("info", f"Mở cửa thủ công từ Web. Lý do: {reason}")
        
        try:
            await post_access_log(name=f"Admin (Lý do: {reason})", method="remote", success=True, image_url="")
        except Exception as e:
            log_app("warning", f"Lỗi ghi log mở cửa từ xa: {e}")

        return web.json_response({"success": True})

    async def handle_lock(request):
        await door_ctrl.lock()
        return web.json_response({"success": True})

    async def handle_stop_alarm(request):
        await alarm_ctrl.stop()
        return web.json_response({"success": True})

    async def handle_test_buzzer(request):
        from config.constants import CMD_TEST_BUZZER
        await uart.send(f"{CMD_TEST_BUZZER}\n")
        return web.json_response({"success": True})

    async def handle_update_pin(request):
        try:
            data = await request.json()
            pin  = data.get("pin", "")
            if not pin or len(pin) < 4:
                return web.json_response({"success": False, "error": "Invalid PIN"}, status=400)
            import hashlib, hmac as _hmac
            secret   = settings.hmac_secret_key.encode("utf-8")
            hmac_hex = _hmac.new(secret, pin.encode("utf-8"), hashlib.sha256).hexdigest()
            await uart.send(f"SET_PIN_HASH:{hmac_hex}\n")
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def handle_update_config(request):
        try:
            data = await request.json()
            
            if "alarm_duration" in data:
                alarm_duration_sec = int(data["alarm_duration"])
                alarm_ctrl.duration = alarm_duration_sec
                log_app("info", f"Cập nhật cấu hình: Còi hú trong {alarm_duration_sec} giây")
                
            if "auto_lock_duration" in data:
                lock_sec_str = str(data["auto_lock_duration"]).lower()
                if "không" in lock_sec_str or "never" in lock_sec_str:
                    lock_sec = 0
                else:
                    lock_sec = int(''.join(filter(str.isdigit, lock_sec_str)))
                
                success = await uart.send(f"SET_TIMEOUT:{lock_sec}\n", expect_ack="ACK_TIMEOUT")
                if success:
                    log_app("info", f"Cấu hình cửa: Tự đóng sau {lock_sec} giây (Đã lưu STM32)")
                else:
                    log_app("warning", "Gửi cấu hình cửa thất bại (Không nhận được ACK từ STM32)")
            
            return web.json_response({"success": True})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=400)

    async def handle_enroll(request):
        data = await request.json()
        asyncio.create_task(enroll(data.get("name"), data.get("id"), num_samples=5))
        return web.json_response({"success": True})

    async def handle_sync_faces(request):
        api_key = request.headers.get("X-Api-Key", "")
        if api_key != settings.api_key:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=403)
        try:
            data    = await request.json()
            log_app(
                "info",
                f"[sync-faces] Push: resident_id={data.get('resident_id')} "
                f"name='{data.get('name')}'",
            )
            result = await handle_sync_push(data)
            return web.json_response(result, status=200 if result["success"] else 500)
        except Exception as exc:
            log_app("error", f"handle_sync_faces: {exc}")
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def handle_delete_face(request):
        api_key = request.headers.get("X-Api-Key", "")
        if api_key != settings.api_key:
            return web.json_response({"success": False, "error": "Unauthorized"}, status=403)
        try:
            data   = await request.json()
            result = await handle_delete_push(data)
            return web.json_response(result)
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)

    async def handle_status(request):
        return web.json_response({
            "door_locked":   True,
            "alarm_active":  alarm_ctrl.is_active,
            "camera_active": shared_camera.is_active,
        })

    async def handle_video_feed(request):
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type":  "multipart/x-mixed-replace; boundary=frame",
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*",
            },
        )
        await response.prepare(request)
        try:
            while True:
                frame = await shared_camera.capture_frame()
                if frame is not None:
                    ret, buf = cv2.imencode(
                        ".jpg", frame[:, :, ::-1],
                        [int(cv2.IMWRITE_JPEG_QUALITY), 60],
                    )
                    if ret:
                        await response.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                            + buf.tobytes()
                            + b"\r\n"
                        )
                await asyncio.sleep(0.033)
        except Exception:
            pass
        return response

    # ── App server ────────────────────────────────────────────────────────────
    app  = web.Application()
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True, expose_headers="*", allow_headers="*"
        )
    })

    cors.add(app.router.add_post("/door/unlock",    handle_unlock))
    cors.add(app.router.add_post("/door/lock",      handle_lock))
    cors.add(app.router.add_post("/alarm/stop",     handle_stop_alarm))
    cors.add(app.router.add_post("/buzzer/test",    handle_test_buzzer))
    cors.add(app.router.add_post("/pin/update",     handle_update_pin))
    cors.add(app.router.add_post("/config/update",  handle_update_config))
    cors.add(app.router.add_post("/camera/enroll",  handle_enroll))
    cors.add(app.router.add_post("/sync-faces",     handle_sync_faces))
    cors.add(app.router.add_post("/delete-face",    handle_delete_face))
    cors.add(app.router.add_get( "/status",         handle_status))
    cors.add(app.router.add_get( "/video_feed",     handle_video_feed))

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 5000).start()
    log_app("info", "Pi API Server ready on :5000")

    # ── Background tasks ───────────────────────────────────────────────────────
    tasks = [
        listen_task, 
        asyncio.create_task(event_dispatcher.dispatch_loop(),  name="event_dispatch"),
        asyncio.create_task(pin_sync_service.run(),            name="pin_sync_w2d"),
        asyncio.create_task(pin_device_svc.run(),              name="pin_sync_d2w"),
        asyncio.create_task(poll_pin_changes(pin_sync_queue),  name="pin_poll"),
        asyncio.create_task(heartbeat_loop(),                  name="heartbeat"),
        asyncio.create_task(state_machine.run(),               name="state_machine"),
        asyncio.create_task(auto_upload_pending_loop(),        name="upload_pending"),
        asyncio.create_task(face_sync_pull_loop(),             name="face_sync_pull"),
    ]

    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            if exc := task.exception():
                log_app("error", f"Task '{task.get_name()}' crashed: {exc}")
    except asyncio.CancelledError:
        pass
    finally:
        for t in tasks:
            t.cancel()
        uart.close()
        await shared_camera.camera_off()
        log_app("info", "System stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")
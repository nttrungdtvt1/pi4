# # # # pi4/control/presence_detector.py
# # # from __future__ import annotations

# # # import asyncio
# # # import time
# # # import base64
# # # import cv2
# # # import numpy as np
# # # import face_recognition
# # # from dataclasses import dataclass
# # # from enum import Enum, auto
# # # from typing import Optional, Callable

# # # from config.settings import settings
# # # from logging_module.event_logger import log_app
# # # from vision.camera_manager import CameraManager
# # # from vision.frame_processor import preprocess # [MỚI] Gọi Kính râm CLAHE chống ngược sáng
# # # from recognition.face_encoder import (
# # #     load_known_faces,
# # #     encode_face,
# # #     compare_faces,
# # #     _ensure_dlib_compatible,
# # # )

# # # # ── Tham số Tuning MỚI (Burst Mode) ───────────────────────────────────────────
# # # WATCH_DURATION     = 5.0   # Tối đa 5s để tìm mặt (Ai lướt qua nhanh quá thì bỏ qua)
# # # SCAN_INTERVAL      = 0.3   # [MỚI] Nghỉ 0.3s giữa các lần quét (Tốc độ súng liên thanh)
# # # MAX_SCAN_RETRIES   = 5     # Quét mặt tối đa 5 lần
# # # FRAME_BROADCAST_INTERVAL = 0.2 # [MỚI] Bắn frame lên Web liên tục mỗi 0.2s cho mượt

# # # class State(Enum):
# # #     IDLE      = auto()
# # #     WATCH     = auto()
# # #     SCANNING  = auto() # Bỏ qua STABILIZE
# # #     GRANTED   = auto()
# # #     DENIED    = auto()

# # # @dataclass
# # # class DetectionResult:
# # #     recognized: bool
# # #     name:       Optional[str] = None
# # #     distance:   float         = 1.0
# # #     confidence: float         = 0.0

# # # class PresenceDetector:
# # #     def __init__(
# # #         self,
# # #         camera:        CameraManager,
# # #         on_recognized: Callable,
# # #         on_unknown:    Callable,
# # #         on_alarm:      Callable,
# # #         broadcast_fn:  Optional[Callable] = None,
# # #         uart_send_fn:  Optional[Callable] = None,
# # #     ):
# # #         self._camera        = camera
# # #         self._on_recognized = on_recognized
# # #         self._on_unknown    = on_unknown
# # #         self._on_alarm      = on_alarm
# # #         self._broadcast     = broadcast_fn
# # #         self._uart_send     = uart_send_fn
# # #         self._state         = State.IDLE
# # #         self._task: Optional[asyncio.Task] = None

# # #     @property
# # #     def state(self) -> State:
# # #         return self._state

# # #     async def on_pir_triggered(self) -> None:
# # #         if self._state != State.IDLE: return
# # #         log_app("info", "[DETECTOR] PIR triggered → WATCH")
# # #         self._state = State.WATCH
# # #         self._task  = asyncio.create_task(self._main_loop())

# # #     # =========================================================================
# # #     # BẮT ĐẦU LUỒNG XỬ LÝ MỚI (SIÊU NHẠY & TRỰC TIẾP)
# # #     # =========================================================================
# # #     async def _main_loop(self) -> None:
# # #         try:
# # #             # 1. Báo Web mở màn hình Live Video ngay lập tức
# # #             await self._emit("face_scan_start", {"state": "watch"})

# # #             # 2. Giai đoạn WATCH (Rất nhanh)
# # #             # Chỉ cần camera tóm được có 1 khuôn mặt trong khung hình là lập tức chuyển sang Quét
# # #             face_found = False
# # #             start_watch = time.monotonic()

# # #             while time.monotonic() - start_watch < WATCH_DURATION:
# # #                 frame = await self._camera.capture_frame()
# # #                 if frame is not None:
# # #                     # Bắn hình lên Web liên tục để khách thấy hình mình
# # #                     await self._broadcast_frame_async(frame, "WATCH")

# # #                     # Kiểm tra xem có mặt người không?
# # #                     box = await self._detect_face_box(frame)
# # #                     if box:
# # #                         face_found = True
# # #                         break # THẤY MẶT LÀ PHÁ VÒNG LẶP NGAY! KHÔNG CHỜ ĐỨNG YÊN.

# # #                 await asyncio.sleep(0.1)

# # #             if not face_found:
# # #                 log_app("info", "[DETECTOR] Không thấy mặt ai → Về ngủ (IDLE)")
# # #                 await self._emit("face_scan_end", {"reason": "no_face"})
# # #                 await self.reset()
# # #                 return

# # #             # 3. Giai đoạn SCAN (Burst Mode 5 lần với Kính chống ngược sáng CLAHE)
# # #             self._state = State.SCANNING
# # #             await self._scan_phase()

# # #         except asyncio.CancelledError:
# # #             pass
# # #         except Exception as exc:
# # #             log_app("error", f"[DETECTOR] Loop error: {exc}")
# # #             await self.reset()

# # #     async def _scan_phase(self) -> None:
# # #         for i in range(1, MAX_SCAN_RETRIES + 1):
# # #             log_app("info", f"[SCAN] Bắn liên thanh lần {i}/{MAX_SCAN_RETRIES}")

# # #             frame = await self._camera.capture_frame()
# # #             if frame is None:
# # #                 await asyncio.sleep(SCAN_INTERVAL)
# # #                 continue

# # #             # [VŨ KHÍ MỚI] Đi qua bộ lọc CLAHE để cứu những bức ảnh bị ngược sáng/tối đen
# # #             processed_frame = preprocess(frame)
# # #             if processed_frame is None:
# # #                 processed_frame = frame # Fallback an toàn

# # #             # Bắn ảnh ĐÃ XỬ LÝ SÁNG lên Web cho người dùng xem
# # #             await self._broadcast_frame_async(processed_frame, "SCANNING", attempt=i)

# # #             # AI So khớp (Sử dụng Dynamic Tolerance bên trong file face_encoder)
# # #             result = await self._recognize(processed_frame)

# # #             if result.recognized:
# # #                 log_app("info", f"[SCAN] SUCCESS: {result.name} (Lệch: {result.distance:.4f})")
# # #                 self._state = State.GRANTED
# # #                 await self._emit("face_recognized", {"name": result.name})
# # #                 await self._on_recognized(result) # Mở cửa
# # #                 await asyncio.sleep(5)
# # #                 await self.reset()
# # #                 return

# # #             # Quét sai -> Ghi log, nghỉ 0.3s rồi bắn tiếp
# # #             await self._on_unknown(result)
# # #             await asyncio.sleep(SCAN_INTERVAL)

# # #         # Trượt cả 5 lần
# # #         log_app("warning", "[SCAN] DENIED -> Intruder Warning & Enable Keypad")
# # #         self._state = State.DENIED
# # #         await self._emit("alarm_intruder_warning", {"detail": "Face recognition failed 5 times"})
# # #         if self._uart_send:
# # #             await self._uart_send("CMD_ENABLE_KEYPAD\n")
# # #         await self._on_alarm()
# # #         await asyncio.sleep(3)
# # #         await self.reset()

# # #     # =========================================================================
# # #     # HÀM PHỤ TRỢ (GIỮ NGUYÊN)
# # #     # =========================================================================
# # #     async def _broadcast_frame_async(self, frame, state, attempt=0):
# # #         try:
# # #             _, buf = cv2.imencode(".jpg", frame[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 50])
# # #             frame_b64 = base64.b64encode(buf).decode("ascii")
# # #             await self._emit("scan_frame", {"frame_b64": frame_b64, "scan_state": state, "attempt": attempt})
# # #         except: pass

# # #     async def _emit(self, event_type: str, data: dict) -> None:
# # #         if self._broadcast:
# # #             await self._broadcast(event_type, data)

# # #     async def _detect_face_box(self, frame: Optional[np.ndarray]) -> Optional[tuple]:
# # #         if frame is None: return None
# # #         loop = asyncio.get_running_loop()
# # #         return await loop.run_in_executor(None, self._detect_sync, frame)

# # #     def _detect_sync(self, frame: np.ndarray) -> Optional[tuple]:
# # #         try:
# # #             img = _ensure_dlib_compatible(frame)
# # #             boxes = face_recognition.face_locations(img, model="hog")
# # #             return boxes[0] if boxes else None
# # #         except: return None

# # #     async def _recognize(self, frame: np.ndarray) -> DetectionResult:
# # #         loop = asyncio.get_running_loop()
# # #         return await loop.run_in_executor(None, self._recog_sync, frame)

# # #     def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
# # #         try:
# # #             known = load_known_faces()
# # #             encs = encode_face(frame)
# # #             if not known or not encs: return DetectionResult(False)
# # #             name, dist = compare_faces(encs[0], known)
# # #             return DetectionResult(name is not None, name, dist, max(0.0, 1.0 - dist))
# # #         except: return DetectionResult(False)

# # #     async def reset(self) -> None:
# # #         self._state = State.IDLE
# # #         if self._task and not self._task.done():
# # #             self._task.cancel()
# # #             try: await self._task
# # #             except asyncio.CancelledError: pass


# # # pi4/control/presence_detector.py
# # from __future__ import annotations

# # import asyncio
# # import time
# # import base64
# # import os
# # import cv2
# # import numpy as np
# # import face_recognition
# # from dataclasses import dataclass
# # from enum import Enum, auto
# # from typing import Optional, Callable

# # from config.settings import settings
# # from logging_module.event_logger import log_app
# # from vision.camera_manager import CameraManager
# # from vision.frame_processor import preprocess
# # from recognition.face_encoder import (
# #     load_known_faces,
# #     encode_face,
# #     compare_faces,
# #     _ensure_dlib_compatible,
# # )

# # WATCH_DURATION     = 5.0
# # SCAN_INTERVAL      = 0.3
# # MAX_SCAN_RETRIES   = 5
# # FRAME_BROADCAST_INTERVAL = 0.2

# # class State(Enum):
# #     IDLE      = auto()
# #     WATCH     = auto()
# #     SCANNING  = auto()
# #     GRANTED   = auto()
# #     DENIED    = auto()

# # @dataclass
# # class DetectionResult:
# #     recognized: bool
# #     name:       Optional[str] = None
# #     distance:   float         = 1.0
# #     confidence: float         = 0.0
# #     image_path: Optional[str] = None # [ĐÃ VÁ LỖI] Khôi phục biến chứa đường dẫn ảnh

# # class PresenceDetector:
# #     def __init__(
# #         self,
# #         camera:        CameraManager,
# #         on_recognized: Callable,
# #         on_unknown:    Callable,
# #         on_alarm:      Callable,
# #         broadcast_fn:  Optional[Callable] = None,
# #         uart_send_fn:  Optional[Callable] = None,
# #     ):
# #         self._camera        = camera
# #         self._on_recognized = on_recognized
# #         self._on_unknown    = on_unknown
# #         self._on_alarm      = on_alarm
# #         self._broadcast     = broadcast_fn
# #         self._uart_send     = uart_send_fn
# #         self._state         = State.IDLE
# #         self._task: Optional[asyncio.Task] = None

# #     @property
# #     def state(self) -> State:
# #         return self._state

# #     async def on_pir_triggered(self) -> None:
# #         if self._state != State.IDLE: return
# #         log_app("info", "[DETECTOR] PIR triggered → WATCH")
# #         self._state = State.WATCH
# #         self._task  = asyncio.create_task(self._main_loop())

# #     async def _main_loop(self) -> None:
# #         try:
# #             await self._emit("face_scan_start", {"state": "watch"})

# #             face_found = False
# #             start_watch = time.monotonic()

# #             while time.monotonic() - start_watch < WATCH_DURATION:
# #                 frame = await self._camera.capture_frame()
# #                 if frame is not None:
# #                     await self._broadcast_frame_async(frame, "WATCH")
# #                     box = await self._detect_face_box(frame)
# #                     if box:
# #                         face_found = True
# #                         break
# #                 await asyncio.sleep(0.1)

# #             if not face_found:
# #                 log_app("info", "[DETECTOR] Không thấy mặt ai → Về ngủ (IDLE)")
# #                 await self._emit("face_scan_end", {"reason": "no_face"})
# #                 await self.reset()
# #                 return

# #             self._state = State.SCANNING
# #             await self._scan_phase()

# #         except asyncio.CancelledError:
# #             pass
# #         except Exception as exc:
# #             log_app("error", f"[DETECTOR] Loop error: {exc}")
# #             await self.reset()

# #     async def _scan_phase(self) -> None:
# #         for i in range(1, MAX_SCAN_RETRIES + 1):
# #             log_app("info", f"[SCAN] Bắn liên thanh lần {i}/{MAX_SCAN_RETRIES}")

# #             frame = await self._camera.capture_frame()
# #             if frame is None:
# #                 await asyncio.sleep(SCAN_INTERVAL)
# #                 continue

# #             processed_frame = preprocess(frame)
# #             if processed_frame is None:
# #                 processed_frame = frame

# #             await self._broadcast_frame_async(processed_frame, "SCANNING", attempt=i)

# #             result = await self._recognize(processed_frame)

# #             # [ĐÃ VÁ LỖI] Lưu bức ảnh vừa quét ra file tạm để sẵn sàng cho việc Upload
# #             temp_img_path = os.path.join(os.getcwd(), "latest_scan.jpg")
# #             cv2.imwrite(temp_img_path, processed_frame[:, :, ::-1])
# #             result.image_path = temp_img_path

# #             if result.recognized:
# #                 log_app("info", f"[SCAN] SUCCESS: {result.name} (Lệch: {result.distance:.4f})")
# #                 self._state = State.GRANTED
# #                 await self._emit("face_recognized", {"name": result.name})
# #                 await self._on_recognized(result)
# #                 await asyncio.sleep(5)
# #                 await self.reset()
# #                 return

# #             await self._on_unknown(result)
# #             await asyncio.sleep(SCAN_INTERVAL)

# #         log_app("warning", "[SCAN] DENIED -> Intruder Warning & Enable Keypad")
# #         self._state = State.DENIED
# #         await self._emit("alarm_intruder_warning", {"detail": "Face recognition failed 5 times"})
# #         if self._uart_send:
# #             await self._uart_send("CMD_ENABLE_KEYPAD\n")
# #         await self._on_alarm()
# #         await asyncio.sleep(3)
# #         await self.reset()

# #     async def _broadcast_frame_async(self, frame, state, attempt=0):
# #         try:
# #             _, buf = cv2.imencode(".jpg", frame[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 50])
# #             frame_b64 = base64.b64encode(buf).decode("ascii")
# #             await self._emit("scan_frame", {"frame_b64": frame_b64, "scan_state": state, "attempt": attempt})
# #         except: pass

# #     async def _emit(self, event_type: str, data: dict) -> None:
# #         if self._broadcast:
# #             await self._broadcast(event_type, data)

# #     async def _detect_face_box(self, frame: Optional[np.ndarray]) -> Optional[tuple]:
# #         if frame is None: return None
# #         loop = asyncio.get_running_loop()
# #         return await loop.run_in_executor(None, self._detect_sync, frame)

# #     def _detect_sync(self, frame: np.ndarray) -> Optional[tuple]:
# #         try:
# #             img = _ensure_dlib_compatible(frame)
# #             boxes = face_recognition.face_locations(img, model="hog")
# #             return boxes[0] if boxes else None
# #         except: return None

# #     async def _recognize(self, frame: np.ndarray) -> DetectionResult:
# #         loop = asyncio.get_running_loop()
# #         return await loop.run_in_executor(None, self._recog_sync, frame)

# #     def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
# #         try:
# #             known = load_known_faces()
# #             encs = encode_face(frame)
# #             if not known or not encs: return DetectionResult(recognized=False)
# #             name, dist = compare_faces(encs[0], known)
# #             return DetectionResult(recognized=(name is not None), name=name, distance=dist, confidence=max(0.0, 1.0 - dist))
# #         except: return DetectionResult(recognized=False)

# #     async def reset(self) -> None:
# #         self._state = State.IDLE
# #         if self._task and not self._task.done():
# #             self._task.cancel()
# #             try: await self._task
# #             except asyncio.CancelledError: pass



# # pi4/control/presence_detector.py
# from __future__ import annotations

# import asyncio
# import time
# import base64
# import os
# import cv2
# import numpy as np
# import face_recognition
# from dataclasses import dataclass
# from enum import Enum, auto
# from typing import Optional, Callable

# from config.settings import settings
# from logging_module.event_logger import log_app
# from vision.camera_manager import CameraManager
# from vision.frame_processor import preprocess
# from recognition.face_encoder import (
#     load_known_faces,
#     encode_face,
#     compare_faces,
#     _ensure_dlib_compatible,
# )

# WATCH_DURATION     = 5.0
# SCAN_INTERVAL      = 0.3
# MAX_SCAN_RETRIES   = 5
# FRAME_BROADCAST_INTERVAL = 0.2

# class State(Enum):
#     IDLE      = auto()
#     WATCH     = auto()
#     SCANNING  = auto()
#     GRANTED   = auto()
#     DENIED    = auto()

# @dataclass
# class DetectionResult:
#     recognized: bool
#     name:       Optional[str] = None
#     distance:   float         = 1.0
#     confidence: float         = 0.0
#     image_path: Optional[str] = None # Khôi phục biến chứa đường dẫn ảnh

# class PresenceDetector:
#     def __init__(
#         self,
#         camera:        CameraManager,
#         on_recognized: Callable,
#         on_unknown:    Callable,
#         on_alarm:      Callable,
#         broadcast_fn:  Optional[Callable] = None,
#         uart_send_fn:  Optional[Callable] = None,
#     ):
#         self._camera        = camera
#         self._on_recognized = on_recognized
#         self._on_unknown    = on_unknown
#         self._on_alarm      = on_alarm
#         self._broadcast     = broadcast_fn
#         self._uart_send     = uart_send_fn
#         self._state         = State.IDLE
#         self._task: Optional[asyncio.Task] = None

#     @property
#     def state(self) -> State:
#         return self._state

#     async def on_pir_triggered(self) -> None:
#         if self._state != State.IDLE: return
#         log_app("info", "[DETECTOR] PIR triggered → WATCH")
#         self._state = State.WATCH
#         self._task  = asyncio.create_task(self._main_loop())

#     async def _main_loop(self) -> None:
#         try:
#             await self._emit("face_scan_start", {"state": "watch"})

#             face_found = False
#             start_watch = time.monotonic()

#             while time.monotonic() - start_watch < WATCH_DURATION:
#                 frame = await self._camera.capture_frame()
#                 if frame is not None:
#                     await self._broadcast_frame_async(frame, "WATCH")
#                     box = await self._detect_face_box(frame)
#                     if box:
#                         face_found = True
#                         break
#                 await asyncio.sleep(0.1)

#             if not face_found:
#                 log_app("info", "[DETECTOR] Không thấy mặt ai → Về ngủ (IDLE)")
#                 await self._emit("face_scan_end", {"reason": "no_face"})
#                 await self.reset()
#                 return

#             self._state = State.SCANNING
#             await self._scan_phase()

#         except asyncio.CancelledError:
#             pass
#         except Exception as exc:
#             log_app("error", f"[DETECTOR] Loop error: {exc}")
#             await self.reset()

#     async def _scan_phase(self) -> None:
#         for i in range(1, MAX_SCAN_RETRIES + 1):
#             log_app("info", f"[SCAN] Bắn liên thanh lần {i}/{MAX_SCAN_RETRIES}")

#             # --- [THÊM MỚI] Gửi lệnh UART xuống STM32 báo đang quét ---
#             if self._uart_send:
#                 await self._uart_send(f"CMD_SCAN_FACE:{i}\n")
#             # -----------------------------------------------------------

#             frame = await self._camera.capture_frame()
#             if frame is None:
#                 await asyncio.sleep(SCAN_INTERVAL)
#                 continue

#             processed_frame = preprocess(frame)
#             if processed_frame is None:
#                 processed_frame = frame

#             await self._broadcast_frame_async(processed_frame, "SCANNING", attempt=i)

#             result = await self._recognize(processed_frame)

#             # Lưu bức ảnh vừa quét ra file tạm để sẵn sàng cho việc Upload
#             temp_img_path = os.path.join(os.getcwd(), "latest_scan.jpg")
#             cv2.imwrite(temp_img_path, processed_frame[:, :, ::-1])
#             result.image_path = temp_img_path

#             if result.recognized:
#                 log_app("info", f"[SCAN] SUCCESS: {result.name} (Lệch: {result.distance:.4f})")
#                 self._state = State.GRANTED
#                 await self._emit("face_recognized", {"name": result.name})
#                 await self._on_recognized(result)
#                 await asyncio.sleep(5)
#                 await self.reset()
#                 return

#             await self._on_unknown(result)
#             await asyncio.sleep(SCAN_INTERVAL)

#         log_app("warning", "[SCAN] DENIED -> Intruder Warning & Enable Keypad")
#         self._state = State.DENIED
#         await self._emit("alarm_intruder_warning", {"detail": "Face recognition failed 5 times"})
#         if self._uart_send:
#             await self._uart_send("CMD_ENABLE_KEYPAD\n")
#         await self._on_alarm()
#         await asyncio.sleep(3)
#         await self.reset()

#     async def _broadcast_frame_async(self, frame, state, attempt=0):
#         try:
#             _, buf = cv2.imencode(".jpg", frame[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 50])
#             frame_b64 = base64.b64encode(buf).decode("ascii")
#             await self._emit("scan_frame", {"frame_b64": frame_b64, "scan_state": state, "attempt": attempt})
#         except: pass

#     async def _emit(self, event_type: str, data: dict) -> None:
#         if self._broadcast:
#             await self._broadcast(event_type, data)

#     async def _detect_face_box(self, frame: Optional[np.ndarray]) -> Optional[tuple]:
#         if frame is None: return None
#         loop = asyncio.get_running_loop()
#         return await loop.run_in_executor(None, self._detect_sync, frame)

#     def _detect_sync(self, frame: np.ndarray) -> Optional[tuple]:
#         try:
#             img = _ensure_dlib_compatible(frame)
#             boxes = face_recognition.face_locations(img, model="hog")
#             return boxes[0] if boxes else None
#         except: return None

#     async def _recognize(self, frame: np.ndarray) -> DetectionResult:
#         loop = asyncio.get_running_loop()
#         return await loop.run_in_executor(None, self._recog_sync, frame)

#     def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
#         try:
#             known = load_known_faces()
#             encs = encode_face(frame)
#             if not known or not encs: return DetectionResult(recognized=False)
#             name, dist = compare_faces(encs[0], known)
#             return DetectionResult(recognized=(name is not None), name=name, distance=dist, confidence=max(0.0, 1.0 - dist))
#         except: return DetectionResult(recognized=False)

#     async def reset(self) -> None:
#         self._state = State.IDLE
#         if self._task and not self._task.done():
#             self._task.cancel()
#             try: await self._task
#             except asyncio.CancelledError: pass



# pi4/control/presence_detector.py
from __future__ import annotations

import asyncio
import time
import base64
import os
import cv2
import numpy as np
import face_recognition
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Callable

from config.settings import settings
from logging_module.event_logger import log_app
from vision.camera_manager import CameraManager
from vision.frame_processor import preprocess
from recognition.face_encoder import (
    load_known_faces,
    encode_face,
    compare_faces,
    _ensure_dlib_compatible,
)

WATCH_DURATION     = 5.0
SCAN_INTERVAL      = 0.3
MAX_SCAN_RETRIES   = 5
FRAME_BROADCAST_INTERVAL = 0.2

class State(Enum):
    IDLE      = auto()
    WATCH     = auto()
    SCANNING  = auto()
    GRANTED   = auto()
    DENIED    = auto()

@dataclass
class DetectionResult:
    recognized: bool
    name:       Optional[str] = None
    distance:   float         = 1.0
    confidence: float         = 0.0
    image_path: Optional[str] = None

class PresenceDetector:
    def __init__(
        self,
        camera:        CameraManager,
        on_recognized: Callable,
        on_unknown:    Callable,
        on_alarm:      Callable,
        broadcast_fn:  Optional[Callable] = None,
        uart_send_fn:  Optional[Callable] = None,
    ):
        self._camera        = camera
        self._on_recognized = on_recognized
        self._on_unknown    = on_unknown
        self._on_alarm      = on_alarm
        self._broadcast     = broadcast_fn
        self._uart_send     = uart_send_fn
        self._state         = State.IDLE
        self._task: Optional[asyncio.Task] = None

    @property
    def state(self) -> State:
        return self._state

    async def on_pir_triggered(self) -> None:
        if self._state != State.IDLE: return
        log_app("info", "[DETECTOR] PIR triggered → WATCH")
        self._state = State.WATCH
        self._task  = asyncio.create_task(self._main_loop())

    async def _main_loop(self) -> None:
        try:
            await self._emit("face_scan_start", {"state": "watch"})

            face_found = False
            start_watch = time.monotonic()

            while time.monotonic() - start_watch < WATCH_DURATION:
                frame = await self._camera.capture_frame()
                if frame is not None:
                    await self._broadcast_frame_async(frame, "WATCH")
                    box = await self._detect_face_box(frame)
                    if box:
                        face_found = True
                        break
                await asyncio.sleep(0.1)

            if not face_found:
                log_app("info", "[DETECTOR] Không thấy mặt ai → Về ngủ (IDLE)")
                await self._emit("face_scan_end", {"reason": "no_face"})
                await self.reset()
                return

            self._state = State.SCANNING
            await self._scan_phase()

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log_app("error", f"[DETECTOR] Loop error: {exc}")
            await self.reset()

    async def _scan_phase(self) -> None:
        last_result = None
        for i in range(1, MAX_SCAN_RETRIES + 1):
            log_app("info", f"[SCAN] Bắn liên thanh lần {i}/{MAX_SCAN_RETRIES}")

            # --- [ĐÃ SỬA] GỬI LỆNH ĐẾM SỐ LẦN XUỐNG STM32 ---
            if self._uart_send:
                await self._uart_send(f"CMD_SCAN_FACE:{i}\n")
            # ------------------------------------------------

            frame = await self._camera.capture_frame()
            if frame is None:
                await asyncio.sleep(SCAN_INTERVAL)
                continue

            processed_frame = preprocess(frame)
            if processed_frame is None:
                processed_frame = frame

            await self._broadcast_frame_async(processed_frame, "SCANNING", attempt=i)

            result = await self._recognize(processed_frame)
            last_result = result

            temp_img_path = os.path.join(os.getcwd(), "latest_scan.jpg")
            cv2.imwrite(temp_img_path, processed_frame[:, :, ::-1])
            result.image_path = temp_img_path

            if result.recognized:
                log_app("info", f"[SCAN] SUCCESS: {result.name} (Lệch: {result.distance:.4f})")
                self._state = State.GRANTED
                await self._emit("face_recognized", {"name": result.name})
                await self._on_recognized(result)
                await asyncio.sleep(5)
                await self.reset()
                return

            # [ĐÃ FIX LỖI SPAM] NẾU QUÉT SAI, CHỈ NGHỈ VÀ QUÉT TIẾP, KHÔNG BẬT KEYPAD VỘI!
            await asyncio.sleep(SCAN_INTERVAL)

        # --- TRƯỢT CẢ 5 LẦN MỚI XỬ LÝ THẤT BẠI 1 LẦN DUY NHẤT ---
        log_app("warning", "[SCAN] DENIED -> Intruder Warning & Enable Keypad")
        self._state = State.DENIED

        if last_result:
            # Hàm này sẽ tự động gọi DoorController để bật còi Bíp và mở khóa màn hình Keypad
            await self._on_unknown(last_result)

        await self._emit("alarm_intruder_warning", {"detail": "Face recognition failed 5 times"})
        await self._on_alarm()
        await asyncio.sleep(3)
        await self.reset()

    async def _broadcast_frame_async(self, frame, state, attempt=0):
        try:
            _, buf = cv2.imencode(".jpg", frame[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 50])
            frame_b64 = base64.b64encode(buf).decode("ascii")
            await self._emit("scan_frame", {"frame_b64": frame_b64, "scan_state": state, "attempt": attempt})
        except: pass

    async def _emit(self, event_type: str, data: dict) -> None:
        if self._broadcast:
            await self._broadcast(event_type, data)

    async def _detect_face_box(self, frame: Optional[np.ndarray]) -> Optional[tuple]:
        if frame is None: return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._detect_sync, frame)

    def _detect_sync(self, frame: np.ndarray) -> Optional[tuple]:
        try:
            img = _ensure_dlib_compatible(frame)
            boxes = face_recognition.face_locations(img, model="hog")
            return boxes[0] if boxes else None
        except: return None

    async def _recognize(self, frame: np.ndarray) -> DetectionResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._recog_sync, frame)

    def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
        try:
            known = load_known_faces()
            encs = encode_face(frame)
            if not known or not encs: return DetectionResult(recognized=False)
            name, dist = compare_faces(encs[0], known)
            return DetectionResult(recognized=(name is not None), name=name, distance=dist, confidence=max(0.0, 1.0 - dist))
        except: return DetectionResult(recognized=False)

    async def reset(self) -> None:
        self._state = State.IDLE
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

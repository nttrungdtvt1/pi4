# # # import asyncio
# # # import time
# # # import cv2
# # # import numpy as np
# # # from enum import Enum, auto
# # # from dataclasses import dataclass
# # # from typing import Optional, Callable, Awaitable
# # # import face_recognition

# # # from config.settings import settings
# # # from logging_module.event_logger import log_app
# # # from vision.camera_manager import CameraManager

# # # # ── CẤU HÌNH THÔNG SỐ ──────────────────────────────────────────────────
# # # WATCH_DURATION     = 5.0    # Chờ xem người đó có đứng lại không
# # # STABILIZE_DURATION = 1.5    # Chờ đứng yên để lấy ảnh nét
# # # SCAN_INTERVAL      = 0.7    # Khoảng nghỉ giữa 5 lần quét (không quá nhanh/chậm)
# # # MAX_SCAN_RETRIES   = 5      # Quét tối đa 5 lần
# # # MIN_FACE_AREA      = 9000   # Diện tích mặt đủ to (đang đứng gần cửa)
# # # MAX_FACE_MOVEMENT  = 50     # Độ xê dịch tâm mặt tối đa giữa các frame (đứng yên)

# # # class State(Enum):
# # #     IDLE      = auto()
# # #     WATCH     = auto()
# # #     STABILIZE = auto()
# # #     SCANNING  = auto()
# # #     GRANTED   = auto()
# # #     DENIED    = auto()

# # # @dataclass
# # # class DetectionResult:
# # #     recognized:  bool
# # #     resident_id: Optional[int] = None
# # #     name:        Optional[str] = None
# # #     confidence:  float = 0.0

# # # class PresenceDetector:
# # #     def __init__(self, camera, on_recognized, on_unknown, on_alarm):
# # #         self._camera = camera
# # #         self._on_recognized = on_recognized
# # #         self._on_unknown = on_unknown
# # #         self._on_alarm = on_alarm
# # #         self._state = State.IDLE
# # #         self._task = None

# # #     async def on_pir_triggered(self):
# # #         if self._state != State.IDLE: return
# # #         log_app("info", "[DETECTOR] Có chuyển động -> WATCH")
# # #         self._state = State.WATCH
# # #         self._task = asyncio.create_task(self._main_loop())

# # #     async def _main_loop(self):
# # #         try:
# # #             # BƯỚC 1: WATCH - Tìm mặt trong 5s
# # #             face_box = await self._watch_phase()
# # #             if not face_box:
# # #                 await self.reset(); return

# # #             # BƯỚC 2: STABILIZE - Chờ đứng yên 1.5s
# # #             is_stable = await self._stabilize_phase(face_box)
# # #             if not is_stable:
# # #                 await self.reset(); return

# # #             # BƯỚC 3: SCANNING - Quét 5 lần
# # #             self._state = State.SCANNING
# # #             await self._scan_phase()

# # #         except Exception as e:
# # #             log_app("error", f"Detector Loop Error: {e}")
# # #             await self.reset()

# # #     async def _watch_phase(self):
# # #         start = time.monotonic()
# # #         count = 0
# # #         while time.monotonic() - start < WATCH_DURATION:
# # #             frame = await self._camera.capture_frame()
# # #             box = await self._detect_box(frame)
# # #             if box:
# # #                 count += 1
# # #                 if count >= 2: return box
# # #             else: count = 0
# # #             await asyncio.sleep(0.2)
# # #         return None

# # #     async def _stabilize_phase(self, last_box):
# # #         self._state = State.STABILIZE
# # #         start = time.monotonic()
# # #         stable_count = 0
# # #         prev_box = last_box
# # #         while time.monotonic() - start < STABILIZE_DURATION:
# # #             frame = await self._camera.capture_frame()
# # #             curr_box = await self._detect_box(frame)
# # #             if curr_box:
# # #                 area = (curr_box[2]-curr_box[0]) * (curr_box[1]-curr_box[3])
# # #                 movement = abs(((curr_box[0]+curr_box[2])/2) - ((prev_box[0]+prev_box[2])/2))
# # #                 if area > MIN_FACE_AREA and movement < MAX_FACE_MOVEMENT:
# # #                     stable_count += 1
# # #                     if stable_count >= 3: return True
# # #                 else: stable_count = 0
# # #                 prev_box = curr_box
# # #             await asyncio.sleep(0.2)
# # #         return False

# # #     async def _scan_phase(self):
# # #         for i in range(1, MAX_SCAN_RETRIES + 1):
# # #             log_app("info", f"[SCAN] Thử lần {i}/{MAX_SCAN_RETRIES}")
# # #             frame = await self._camera.capture_frame()
# # #             # Chọn frame nét nhất trong 3 frame nhỏ
# # #             best_frame = await self._get_best_of_n(3)
# # #             result = await self._recognize(best_frame)

# # #             if result.recognized:
# # #                 log_app("info", f"[SUCCESS] Chào {result.name}")
# # #                 self._state = State.GRANTED
# # #                 await self._on_recognized(result)
# # #                 await asyncio.sleep(5) # Chờ người ta vào nhà
# # #                 await self.reset(); return

# # #             await self._on_unknown(result)
# # #             if i < MAX_SCAN_RETRIES:
# # #                 await asyncio.sleep(SCAN_INTERVAL)

# # #         log_app("warn", "[FAILED] Không nhận diện được sau 5 lần")
# # #         self._state = State.DENIED
# # #         await self._on_alarm()
# # #         await asyncio.sleep(3)
# # #         await self.reset()

# # #     async def _detect_box(self, frame):
# # #         loop = asyncio.get_running_loop()
# # #         return await loop.run_in_executor(None, self._detect_sync, frame)

# # #     def _detect_sync(self, frame):
# # #         rgb = frame[:, :, ::-1]
# # #         boxes = face_recognition.face_locations(rgb, model="hog")
# # #         return boxes[0] if boxes else None

# # #     async def _get_best_of_n(self, n):
# # #         frames = []
# # #         for _ in range(n):
# # #             f = await self._camera.capture_frame()
# # #             if f is not None:
# # #                 lap = cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
# # #                 frames.append((lap, f))
# # #             await asyncio.sleep(0.1)
# # #         return max(frames, key=lambda x: x[0])[1] if frames else None

# # #     async def _recognize(self, frame):
# # #         loop = asyncio.get_running_loop()
# # #         return await loop.run_in_executor(None, self._recog_sync, frame)

# # #     def _recog_sync(self, frame):
# # #         # Giả định bạn đã có logic load encodings từ file json như trước
# # #         import json
# # #         from pathlib import Path
# # #         try:
# # #             with open(settings.encodings_path) as f:
# # #                 db = json.load(f)
# # #             known_enc = [item["encoding"] for item in db]
# # #             rgb = frame[:, :, ::-1]
# # #             locs = face_recognition.face_locations(rgb, model="hog")
# # #             if not locs: return DetectionResult(False)
# # #             enc = face_recognition.face_encodings(rgb, locs)[0]
# # #             dists = face_recognition.face_distance(known_enc, enc)
# # #             idx = np.argmin(dists)
# # #             if dists[idx] <= settings.face_tolerance:
# # #                 return DetectionResult(True, db[idx]["id"], db[idx]["name"], 1-dists[idx])
# # #         except: pass
# # #         return DetectionResult(False)

# # #     async def reset(self):
# # #         self._state = State.IDLE
# # #         if self._task: self._task.cancel()




# # # # # # pi4/control/presence_detector.py
# # # # # """
# # # # # THIẾT KẾ MỚI — Đơn giản, rõ ràng, không bug ẩn.

# # # # # LUỒNG HOẠT ĐỘNG:
# # # # #   PIR trigger
# # # # #     → WATCH: Tìm mặt trong khung hình (tối đa 5s)
# # # # #     → STABILIZE: Chờ người đứng yên (1.5s)
# # # # #     → SCAN: Nhận diện tối đa 5 lần
# # # # #       → Nhận ra → mở cửa
# # # # #       → Không nhận ra → cảnh báo → kích hoạt báo động

# # # # # CÁC SỬA ĐỔI SO VỚI CODE CŨ:
# # # # #   - _detect_sync(): dùng _ensure_dlib_compatible() trước khi gọi face_locations
# # # # #   - _recog_sync(): đọc từ known_faces.pkl (không phải JSON), dùng face_encoder mới
# # # # #   - Bỏ _read_json_db() bị nhầm lẫn format với backend DB
# # # # #   - Thêm load_known_faces() cache đúng cách
# # # # # """
# # # # # from __future__ import annotations

# # # # # import asyncio
# # # # # import time
# # # # # from dataclasses import dataclass
# # # # # from enum import Enum, auto
# # # # # from typing import Optional, Callable

# # # # # import cv2
# # # # # import numpy as np
# # # # # import face_recognition

# # # # # from logging_module.event_logger import log_app
# # # # # from vision.camera_manager import CameraManager
# # # # # from recognition.face_encoder import (
# # # # #     load_known_faces,
# # # # #     encode_face,
# # # # #     compare_faces,
# # # # #     _ensure_dlib_compatible,
# # # # # )

# # # # # # ── Tham số ───────────────────────────────────────────────────────────────────
# # # # # WATCH_DURATION = 5.0        # Chờ tối đa 5s để tìm mặt trong frame
# # # # # STABILIZE_DURATION = 1.5    # Chờ đứng yên 1.5s trước khi scan
# # # # # SCAN_INTERVAL = 0.7         # Nghỉ 0.7s giữa các lần scan
# # # # # MAX_SCAN_RETRIES = 5        # Quét tối đa 5 lần
# # # # # MIN_FACE_AREA = 6000        # Diện tích pixel tối thiểu (đứng đủ gần)
# # # # # MAX_FACE_MOVEMENT = 60      # Pixel di chuyển tối đa giữa 2 frame (đứng yên)


# # # # # class State(Enum):
# # # # #     IDLE = auto()
# # # # #     WATCH = auto()
# # # # #     STABILIZE = auto()
# # # # #     SCANNING = auto()
# # # # #     GRANTED = auto()
# # # # #     DENIED = auto()


# # # # # @dataclass
# # # # # class DetectionResult:
# # # # #     recognized: bool
# # # # #     name: Optional[str] = None
# # # # #     distance: float = 1.0
# # # # #     confidence: float = 0.0


# # # # # class PresenceDetector:
# # # # #     def __init__(
# # # # #         self,
# # # # #         camera: CameraManager,
# # # # #         on_recognized: Callable,
# # # # #         on_unknown: Callable,
# # # # #         on_alarm: Callable,
# # # # #     ):
# # # # #         self._camera = camera
# # # # #         self._on_recognized = on_recognized
# # # # #         self._on_unknown = on_unknown
# # # # #         self._on_alarm = on_alarm
# # # # #         self._state = State.IDLE
# # # # #         self._task: Optional[asyncio.Task] = None

# # # # #     # ── Entry point từ PIR ────────────────────────────────────────────────────

# # # # #     async def on_pir_triggered(self) -> None:
# # # # #         if self._state != State.IDLE:
# # # # #             return
# # # # #         log_app("info", "[DETECTOR] PIR triggered → WATCH")
# # # # #         self._state = State.WATCH
# # # # #         self._task = asyncio.create_task(self._main_loop())

# # # # #     # ── Vòng lặp chính ────────────────────────────────────────────────────────

# # # # #     async def _main_loop(self) -> None:
# # # # #         try:
# # # # #             face_box = await self._watch_phase()
# # # # #             if not face_box:
# # # # #                 log_app("info", "[DETECTOR] No face in WATCH → back to IDLE")
# # # # #                 await self.reset()
# # # # #                 return

# # # # #             stable = await self._stabilize_phase(face_box)
# # # # #             if not stable:
# # # # #                 log_app("info", "[DETECTOR] Not stable → back to IDLE")
# # # # #                 await self.reset()
# # # # #                 return

# # # # #             self._state = State.SCANNING
# # # # #             await self._scan_phase()

# # # # #         except asyncio.CancelledError:
# # # # #             pass
# # # # #         except Exception as exc:
# # # # #             log_app("error", f"[DETECTOR] Main loop error: {exc}")
# # # # #             await self.reset()

# # # # #     # ── WATCH: tìm mặt trong 5s ──────────────────────────────────────────────

# # # # #     async def _watch_phase(self) -> Optional[tuple]:
# # # # #         start = time.monotonic()
# # # # #         consecutive = 0

# # # # #         while time.monotonic() - start < WATCH_DURATION:
# # # # #             frame = await self._camera.capture_frame()
# # # # #             box = await self._detect_face_box(frame)
# # # # #             if box:
# # # # #                 consecutive += 1
# # # # #                 if consecutive >= 2:  # Thấy mặt 2 frame liên tiếp → chắc chắn có người
# # # # #                     return box
# # # # #             else:
# # # # #                 consecutive = 0
# # # # #             await asyncio.sleep(0.2)

# # # # #         return None

# # # # #     # ── STABILIZE: chờ đứng yên ──────────────────────────────────────────────

# # # # #     async def _stabilize_phase(self, last_box: tuple) -> bool:
# # # # #         self._state = State.STABILIZE
# # # # #         start = time.monotonic()
# # # # #         stable_count = 0
# # # # #         prev_box = last_box

# # # # #         while time.monotonic() - start < STABILIZE_DURATION:
# # # # #             frame = await self._camera.capture_frame()
# # # # #             curr_box = await self._detect_face_box(frame)

# # # # #             if curr_box:
# # # # #                 top, right, bottom, left = curr_box
# # # # #                 area = abs((bottom - top) * (right - left))
# # # # #                 prev_cx = (prev_box[3] + prev_box[1]) / 2
# # # # #                 curr_cx = (left + right) / 2
# # # # #                 movement = abs(curr_cx - prev_cx)

# # # # #                 if area >= MIN_FACE_AREA and movement <= MAX_FACE_MOVEMENT:
# # # # #                     stable_count += 1
# # # # #                     if stable_count >= 3:
# # # # #                         return True
# # # # #                 else:
# # # # #                     stable_count = 0

# # # # #                 prev_box = curr_box

# # # # #             await asyncio.sleep(0.2)

# # # # #         return False

# # # # #     # ── SCAN: nhận diện tối đa 5 lần ─────────────────────────────────────────

# # # # #     async def _scan_phase(self) -> None:
# # # # #         for i in range(1, MAX_SCAN_RETRIES + 1):
# # # # #             log_app("info", f"[SCAN] Attempt {i}/{MAX_SCAN_RETRIES}")

# # # # #             # Lấy frame nét nhất trong 3 frame
# # # # #             best_frame = await self._get_sharpest_frame(n=3)
# # # # #             if best_frame is None:
# # # # #                 await asyncio.sleep(SCAN_INTERVAL)
# # # # #                 continue

# # # # #             result = await self._recognize(best_frame)

# # # # #             if result.recognized:
# # # # #                 log_app("info", f"[SCAN] GRANTED: {result.name} (dist={result.distance:.4f})")
# # # # #                 self._state = State.GRANTED
# # # # #                 await self._on_recognized(result)
# # # # #                 await asyncio.sleep(5)  # Cooldown — người đi vào nhà
# # # # #                 await self.reset()
# # # # #                 return

# # # # #             log_app("info", f"[SCAN] UNKNOWN (best_dist={result.distance:.4f})")
# # # # #             await self._on_unknown(result)

# # # # #             if i < MAX_SCAN_RETRIES:
# # # # #                 await asyncio.sleep(SCAN_INTERVAL)

# # # # #         log_app("warning", "[SCAN] DENIED after max retries → alarm")
# # # # #         self._state = State.DENIED
# # # # #         await self._on_alarm()
# # # # #         await asyncio.sleep(3)
# # # # #         await self.reset()

# # # # #     # ── Helpers ───────────────────────────────────────────────────────────────

# # # # #     async def _detect_face_box(self, frame: Optional[np.ndarray]) -> Optional[tuple]:
# # # # #         """Detect box khuôn mặt trong frame. Chạy trên ThreadPool."""
# # # # #         if frame is None:
# # # # #             return None
# # # # #         loop = asyncio.get_running_loop()
# # # # #         return await loop.run_in_executor(None, self._detect_sync, frame)

# # # # #     def _detect_sync(self, frame: np.ndarray) -> Optional[tuple]:
# # # # #         """Blocking — chạy trong thread pool."""
# # # # #         try:
# # # # #             img = _ensure_dlib_compatible(frame)
# # # # #             boxes = face_recognition.face_locations(img, model="hog",
# # # # #                                                     number_of_times_to_upsample=1)
# # # # #             return boxes[0] if boxes else None
# # # # #         except Exception as exc:
# # # # #             log_app("debug", f"_detect_sync error: {exc}")
# # # # #             return None

# # # # #     async def _get_sharpest_frame(self, n: int = 3) -> Optional[np.ndarray]:
# # # # #         """Chọn frame sắc nét nhất (Laplacian variance cao nhất) trong n frame."""
# # # # #         candidates = []
# # # # #         for _ in range(n):
# # # # #             frame = await self._camera.capture_frame()
# # # # #             if frame is not None:
# # # # #                 gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
# # # # #                 sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
# # # # #                 candidates.append((sharpness, frame))
# # # # #             await asyncio.sleep(0.1)

# # # # #         if not candidates:
# # # # #             return None
# # # # #         return max(candidates, key=lambda x: x[0])[1]

# # # # #     async def _recognize(self, frame: np.ndarray) -> DetectionResult:
# # # # #         """Nhận diện mặt trong frame. Chạy trên ThreadPool."""
# # # # #         loop = asyncio.get_running_loop()
# # # # #         return await loop.run_in_executor(None, self._recog_sync, frame)

# # # # #     def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
# # # # #         """
# # # # #         Blocking recognition — chạy trong thread pool.
# # # # #         Đọc từ known_faces.pkl (cache RAM), không đọc disk mỗi lần.
# # # # #         """
# # # # #         try:
# # # # #             known = load_known_faces()
# # # # #             if not known:
# # # # #                 log_app("warning", "No enrolled faces — recognition skipped")
# # # # #                 return DetectionResult(recognized=False, distance=1.0)

# # # # #             encodings = encode_face(frame)
# # # # #             if not encodings:
# # # # #                 return DetectionResult(recognized=False, distance=1.0)

# # # # #             name, distance = compare_faces(encodings[0], known)
# # # # #             confidence = max(0.0, 1.0 - distance)

# # # # #             return DetectionResult(
# # # # #                 recognized=(name is not None),
# # # # #                 name=name,
# # # # #                 distance=distance,
# # # # #                 confidence=confidence,
# # # # #             )

# # # # #         except Exception as exc:
# # # # #             log_app("error", f"_recog_sync error: {exc}")
# # # # #             return DetectionResult(recognized=False, distance=1.0)

# # # # #     async def reset(self) -> None:
# # # # #         self._state = State.IDLE
# # # # #         if self._task and not self._task.done():
# # # # #             self._task.cancel()
# # # # #             try:
# # # # #                 await self._task
# # # # #             except asyncio.CancelledError:
# # # # #                 pass

# # # # #     @property
# # # # #     def state(self) -> State:
# # # # #         return self._state

# # # # # pi4/control/presence_detector.py
# # # # """
# # # # COMPLETE REWRITE v3 — Fixes:

# # # # [FIX-LIVE-STREAM] Pi now broadcasts camera frames to backend via HTTP during
# # # #   WATCH/STABILIZE/SCAN phases. Backend re-broadcasts over WebSocket to Dashboard.

# # # #   Flow:
# # # #     frame captured → POST /api/events  type="scan_frame"  data={frame_b64, state}
# # # #     Backend → WS broadcast → Dashboard renders real-time frames

# # # # [FIX-DATASET] After successful recognition, saves frame to:
# # # #     pi4/data/dataset/{resident_name}/{timestamp}.jpg
# # # #   This creates a local dataset for future retraining/debugging.

# # # # [KEEP] Full detection logic: WATCH → STABILIZE → SCAN → GRANTED/DENIED
# # # # [KEEP] UART communication for door unlock
# # # # [KEEP] All tolerances, retry counts, state transitions

# # # # NOTES ON MODEL CHOICE:
# # # #   Keeping face_recognition (dlib HOG). InsightFace requires 300MB+ ONNX models
# # # #   and complex ARM build — too risky for embedded production. dlib HOG on Pi 4:
# # # #   ~200ms/frame @ 640×480, accuracy sufficient with tolerance=0.45.

# # # # BROADCAST PROTOCOL:
# # # #   Pi → POST http://{backend}:8000/api/events/
# # # #   {
# # # #     "type": "scan_frame",
# # # #     "payload": {
# # # #       "frame_b64": "<JPEG as base64>",
# # # #       "scan_state": "WATCH"|"STABILIZE"|"SCAN",
# # # #       "attempt": 1
# # # #     }
# # # #   }
# # # #   Backend broadcasts to all WS clients → Frontend CameraSnapshot renders it.
# # # # """
# # # # from __future__ import annotations

# # # # import asyncio
# # # # import base64
# # # # import time
# # # # from dataclasses import dataclass
# # # # from datetime import datetime
# # # # from enum import Enum, auto
# # # # from pathlib import Path
# # # # from typing import Optional, Callable

# # # # import cv2
# # # # import numpy as np
# # # # import face_recognition

# # # # from config.settings import settings
# # # # from logging_module.event_logger import log_app
# # # # from vision.camera_manager import CameraManager
# # # # from recognition.face_encoder import (
# # # #     load_known_faces,
# # # #     encode_face,
# # # #     compare_faces,
# # # #     _ensure_dlib_compatible,
# # # # )

# # # # # ── Tuning parameters ─────────────────────────────────────────────────────────

# # # # WATCH_DURATION       = 5.0   # Chờ tối đa 5s để tìm mặt trong frame
# # # # STABILIZE_DURATION   = 1.5   # Chờ đứng yên 1.5s trước khi scan
# # # # SCAN_INTERVAL        = 0.7   # Nghỉ 0.7s giữa các lần scan
# # # # MAX_SCAN_RETRIES     = 5     # Quét tối đa 5 lần
# # # # MIN_FACE_AREA        = 6000  # Diện tích pixel tối thiểu (đứng đủ gần)
# # # # MAX_FACE_MOVEMENT    = 60    # Pixel di chuyển tối đa giữa 2 frame (đứng yên)

# # # # # Frame broadcast interval during scan phases (seconds)
# # # # FRAME_BROADCAST_INTERVAL = 0.35


# # # # class State(Enum):
# # # #     IDLE      = auto()
# # # #     WATCH     = auto()
# # # #     STABILIZE = auto()
# # # #     SCANNING  = auto()
# # # #     GRANTED   = auto()
# # # #     DENIED    = auto()


# # # # @dataclass
# # # # class DetectionResult:
# # # #     recognized: bool
# # # #     name:       Optional[str] = None
# # # #     distance:   float         = 1.0
# # # #     confidence: float         = 0.0
# # # #     image_path: Optional[str] = None


# # # # class PresenceDetector:
# # # #     def __init__(
# # # #         self,
# # # #         camera: CameraManager,
# # # #         on_recognized: Callable,
# # # #         on_unknown: Callable,
# # # #         on_alarm: Callable,
# # # #     ):
# # # #         self._camera       = camera
# # # #         self._on_recognized = on_recognized
# # # #         self._on_unknown   = on_unknown
# # # #         self._on_alarm     = on_alarm
# # # #         self._state        = State.IDLE
# # # #         self._task: Optional[asyncio.Task] = None

# # # #     # ── Entry point ───────────────────────────────────────────────────────────

# # # #     async def on_pir_triggered(self) -> None:
# # # #         if self._state != State.IDLE:
# # # #             return
# # # #         log_app("info", "[DETECTOR] PIR triggered → WATCH")
# # # #         self._state = State.WATCH
# # # #         self._task  = asyncio.create_task(self._main_loop())

# # # #     # ── Main loop ─────────────────────────────────────────────────────────────

# # # #     async def _main_loop(self) -> None:
# # # #         try:
# # # #             # Notify backend: scanning started
# # # #             await self._broadcast_state_event("scan_started", {})

# # # #             face_box = await self._watch_phase()
# # # #             if not face_box:
# # # #                 log_app("info", "[DETECTOR] No face in WATCH → back to IDLE")
# # # #                 await self._broadcast_state_event("scan_ended", {"reason": "no_face"})
# # # #                 await self.reset()
# # # #                 return

# # # #             stable = await self._stabilize_phase(face_box)
# # # #             if not stable:
# # # #                 log_app("info", "[DETECTOR] Not stable → back to IDLE")
# # # #                 await self._broadcast_state_event("scan_ended", {"reason": "unstable"})
# # # #                 await self.reset()
# # # #                 return

# # # #             self._state = State.SCANNING
# # # #             await self._scan_phase()

# # # #         except asyncio.CancelledError:
# # # #             pass
# # # #         except Exception as exc:
# # # #             log_app("error", f"[DETECTOR] Main loop error: {exc}")
# # # #             await self.reset()

# # # #     # ── WATCH: find face in 5s ────────────────────────────────────────────────

# # # #     async def _watch_phase(self) -> Optional[tuple]:
# # # #         start       = time.monotonic()
# # # #         consecutive = 0
# # # #         last_broadcast = 0.0

# # # #         while time.monotonic() - start < WATCH_DURATION:
# # # #             frame = await self._camera.capture_frame()

# # # #             # [FIX-LIVE-STREAM] Broadcast frame to Dashboard
# # # #             now = time.monotonic()
# # # #             if frame is not None and (now - last_broadcast) >= FRAME_BROADCAST_INTERVAL:
# # # #                 await self._broadcast_frame(frame, "WATCH")
# # # #                 last_broadcast = now

# # # #             box = await self._detect_face_box(frame)
# # # #             if box:
# # # #                 consecutive += 1
# # # #                 if consecutive >= 2:
# # # #                     return box
# # # #             else:
# # # #                 consecutive = 0
# # # #             await asyncio.sleep(0.2)

# # # #         return None

# # # #     # ── STABILIZE: wait for stillness ────────────────────────────────────────

# # # #     async def _stabilize_phase(self, last_box: tuple) -> bool:
# # # #         self._state   = State.STABILIZE
# # # #         start         = time.monotonic()
# # # #         stable_count  = 0
# # # #         prev_box      = last_box
# # # #         last_broadcast = 0.0

# # # #         while time.monotonic() - start < STABILIZE_DURATION:
# # # #             frame = await self._camera.capture_frame()

# # # #             # [FIX-LIVE-STREAM] Broadcast frame
# # # #             now = time.monotonic()
# # # #             if frame is not None and (now - last_broadcast) >= FRAME_BROADCAST_INTERVAL:
# # # #                 await self._broadcast_frame(frame, "STABILIZE")
# # # #                 last_broadcast = now

# # # #             curr_box = await self._detect_face_box(frame)
# # # #             if curr_box:
# # # #                 top, right, bottom, left = curr_box
# # # #                 area     = abs((bottom - top) * (right - left))
# # # #                 prev_cx  = (prev_box[3] + prev_box[1]) / 2
# # # #                 curr_cx  = (left + right) / 2
# # # #                 movement = abs(curr_cx - prev_cx)

# # # #                 if area >= MIN_FACE_AREA and movement <= MAX_FACE_MOVEMENT:
# # # #                     stable_count += 1
# # # #                     if stable_count >= 3:
# # # #                         return True
# # # #                 else:
# # # #                     stable_count = 0

# # # #                 prev_box = curr_box

# # # #             await asyncio.sleep(0.2)

# # # #         return False

# # # #     # ── SCAN: recognize up to MAX_SCAN_RETRIES times ──────────────────────────

# # # #     async def _scan_phase(self) -> None:
# # # #         for i in range(1, MAX_SCAN_RETRIES + 1):
# # # #             log_app("info", f"[SCAN] Attempt {i}/{MAX_SCAN_RETRIES}")

# # # #             # Get sharpest frame from n=3 captures
# # # #             best_frame = await self._get_sharpest_frame(n=3)
# # # #             if best_frame is None:
# # # #                 await asyncio.sleep(SCAN_INTERVAL)
# # # #                 continue

# # # #             # [FIX-LIVE-STREAM] Broadcast best frame with attempt counter
# # # #             await self._broadcast_frame(best_frame, "SCAN", attempt=i)

# # # #             result = await self._recognize(best_frame)

# # # #             if result.recognized:
# # # #                 log_app("info", f"[SCAN] GRANTED: {result.name} (dist={result.distance:.4f})")

# # # #                 # [FIX-DATASET] Save recognized frame to dataset
# # # #                 saved_path = await self._save_dataset_image(best_frame, result.name)
# # # #                 result.image_path = saved_path

# # # #                 self._state = State.GRANTED
# # # #                 await self._broadcast_state_event("scan_ended", {
# # # #                     "reason":     "recognized",
# # # #                     "name":       result.name,
# # # #                     "confidence": round(result.confidence, 4),
# # # #                 })
# # # #                 await self._on_recognized(result)
# # # #                 await asyncio.sleep(5)  # Cooldown
# # # #                 await self.reset()
# # # #                 return

# # # #             log_app("info", f"[SCAN] UNKNOWN (best_dist={result.distance:.4f})")

# # # #             # [FIX-DATASET] Save unknown frame for later review
# # # #             await self._save_dataset_image(best_frame, "unknown")

# # # #             await self._on_unknown(result)

# # # #             if i < MAX_SCAN_RETRIES:
# # # #                 await asyncio.sleep(SCAN_INTERVAL)

# # # #         log_app("warning", "[SCAN] DENIED after max retries → alarm")
# # # #         self._state = State.DENIED
# # # #         await self._broadcast_state_event("scan_ended", {"reason": "denied"})
# # # #         await self._on_alarm()
# # # #         await asyncio.sleep(3)
# # # #         await self.reset()

# # # #     # ── Frame broadcasting ────────────────────────────────────────────────────

# # # #     async def _broadcast_frame(
# # # #         self,
# # # #         frame: np.ndarray,
# # # #         scan_state: str,
# # # #         attempt: int = 0,
# # # #     ) -> None:
# # # #         """
# # # #         [FIX-LIVE-STREAM] Encode frame to JPEG base64 and POST to backend.
# # # #         Backend broadcasts to all WS clients → Dashboard renders in real-time.

# # # #         Non-blocking: runs on executor, errors are swallowed (stream degradation
# # # #         is acceptable — never block recognition pipeline).
# # # #         """
# # # #         try:
# # # #             loop = asyncio.get_running_loop()
# # # #             await loop.run_in_executor(
# # # #                 None,
# # # #                 self._post_frame_sync,
# # # #                 frame.copy(),
# # # #                 scan_state,
# # # #                 attempt,
# # # #             )
# # # #         except Exception as exc:
# # # #             log_app("debug", f"[DETECTOR] Frame broadcast error: {exc}")

# # # #     def _post_frame_sync(
# # # #         self,
# # # #         frame: np.ndarray,
# # # #         scan_state: str,
# # # #         attempt: int,
# # # #     ) -> None:
# # # #         """Blocking POST — runs in thread pool."""
# # # #         import requests
# # # #         try:
# # # #             # Encode frame to JPEG (quality 60 — sufficient for live preview)
# # # #             bgr = frame[:, :, ::-1]  # RGB → BGR for cv2
# # # #             ret, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 60])
# # # #             if not ret:
# # # #                 return

# # # #             frame_b64 = base64.b64encode(buf.tobytes()).decode("ascii")

# # # #             url     = f"{settings.api_server_url}/api/events/"
# # # #             headers = {
# # # #                 "X-Pi-Api-Key": settings.api_key,
# # # #                 "Content-Type": "application/json",
# # # #             }
# # # #             payload = {
# # # #                 "type": "scan_frame",
# # # #                 "payload": {
# # # #                     "frame_b64":  frame_b64,
# # # #                     "scan_state": scan_state,
# # # #                     "attempt":    attempt,
# # # #                 },
# # # #                 "timestamp": datetime.now().isoformat(),
# # # #             }
# # # #             requests.post(url, json=payload, headers=headers, timeout=1.5)

# # # #         except Exception as exc:
# # # #             log_app("debug", f"[DETECTOR] _post_frame_sync: {exc}")

# # # #     async def _broadcast_state_event(self, event_type: str, data: dict) -> None:
# # # #         """Broadcast scan lifecycle events (scan_started, scan_ended)."""
# # # #         try:
# # # #             import aiohttp
# # # #             url     = f"{settings.api_server_url}/api/events/"
# # # #             headers = {
# # # #                 "X-Pi-Api-Key": settings.api_key,
# # # #                 "Content-Type": "application/json",
# # # #             }
# # # #             payload = {
# # # #                 "type":      event_type,
# # # #                 "payload":   data,
# # # #                 "timestamp": datetime.now().isoformat(),
# # # #             }
# # # #             async with aiohttp.ClientSession() as session:
# # # #                 async with session.post(
# # # #                     url, json=payload, headers=headers,
# # # #                     timeout=aiohttp.ClientTimeout(total=3.0),
# # # #                 ) as resp:
# # # #                     log_app("debug", f"[DETECTOR] state event {event_type} → HTTP {resp.status}")
# # # #         except Exception as exc:
# # # #             log_app("debug", f"[DETECTOR] _broadcast_state_event: {exc}")

# # # #     # ── Dataset save ──────────────────────────────────────────────────────────

# # # #     async def _save_dataset_image(
# # # #         self,
# # # #         frame: np.ndarray,
# # # #         name: str,
# # # #     ) -> Optional[str]:
# # # #         """
# # # #         [FIX-DATASET] Save captured frame to:
# # # #           pi4/data/dataset/{name}/{YYYYMMDD_HHMMSS_ffffff}.jpg

# # # #         Returns saved path or None on error.
# # # #         """
# # # #         try:
# # # #             loop = asyncio.get_running_loop()
# # # #             return await loop.run_in_executor(
# # # #                 None, self._save_dataset_sync, frame.copy(), name
# # # #             )
# # # #         except Exception as exc:
# # # #             log_app("warning", f"[DETECTOR] Dataset save error: {exc}")
# # # #             return None

# # # #     def _save_dataset_sync(self, frame: np.ndarray, name: str) -> Optional[str]:
# # # #         """Blocking save — runs in thread pool."""
# # # #         try:
# # # #             # Sanitize name for filesystem
# # # #             safe_name = "".join(
# # # #                 c if c.isalnum() or c in ("_", "-") else "_"
# # # #                 for c in (name or "unknown")
# # # #             )
# # # #             dataset_dir = settings.encodings_path.parent / "dataset" / safe_name
# # # #             dataset_dir.mkdir(parents=True, exist_ok=True)

# # # #             ts       = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
# # # #             img_path = dataset_dir / f"{ts}.jpg"

# # # #             bgr = frame[:, :, ::-1]  # RGB → BGR
# # # #             cv2.imwrite(str(img_path), bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])

# # # #             log_app("info", f"[DETECTOR] Dataset image saved: {img_path}")
# # # #             return str(img_path)

# # # #         except Exception as exc:
# # # #             log_app("error", f"[DETECTOR] _save_dataset_sync: {exc}")
# # # #             return None

# # # #     # ── Face detection helpers ────────────────────────────────────────────────

# # # #     async def _detect_face_box(
# # # #         self, frame: Optional[np.ndarray]
# # # #     ) -> Optional[tuple]:
# # # #         if frame is None:
# # # #             return None
# # # #         loop = asyncio.get_running_loop()
# # # #         return await loop.run_in_executor(None, self._detect_sync, frame)

# # # #     def _detect_sync(self, frame: np.ndarray) -> Optional[tuple]:
# # # #         """Blocking — runs in thread pool."""
# # # #         try:
# # # #             img   = _ensure_dlib_compatible(frame)
# # # #             boxes = face_recognition.face_locations(
# # # #                 img, model="hog", number_of_times_to_upsample=1
# # # #             )
# # # #             return boxes[0] if boxes else None
# # # #         except Exception as exc:
# # # #             log_app("debug", f"_detect_sync error: {exc}")
# # # #             return None

# # # #     async def _get_sharpest_frame(self, n: int = 3) -> Optional[np.ndarray]:
# # # #         """Pick the sharpest frame (highest Laplacian variance) from n frames."""
# # # #         candidates = []
# # # #         for _ in range(n):
# # # #             frame = await self._camera.capture_frame()
# # # #             if frame is not None:
# # # #                 gray      = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
# # # #                 sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
# # # #                 candidates.append((sharpness, frame))
# # # #             await asyncio.sleep(0.1)

# # # #         if not candidates:
# # # #             return None
# # # #         return max(candidates, key=lambda x: x[0])[1]

# # # #     async def _recognize(self, frame: np.ndarray) -> DetectionResult:
# # # #         loop = asyncio.get_running_loop()
# # # #         return await loop.run_in_executor(None, self._recog_sync, frame)

# # # #     def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
# # # #         """
# # # #         Blocking recognition — reads from known_faces.pkl RAM cache.
# # # #         force_reload=False: use cached data unless sync service updated pkl.
# # # #         """
# # # #         try:
# # # #             known = load_known_faces()
# # # #             if not known:
# # # #                 log_app("warning", "No enrolled faces — recognition skipped")
# # # #                 return DetectionResult(recognized=False, distance=1.0)

# # # #             encodings = encode_face(frame)
# # # #             if not encodings:
# # # #                 return DetectionResult(recognized=False, distance=1.0)

# # # #             name, distance = compare_faces(encodings[0], known)
# # # #             confidence     = max(0.0, 1.0 - distance)

# # # #             return DetectionResult(
# # # #                 recognized=(name is not None),
# # # #                 name=name,
# # # #                 distance=distance,
# # # #                 confidence=confidence,
# # # #             )

# # # #         except Exception as exc:
# # # #             log_app("error", f"_recog_sync error: {exc}")
# # # #             return DetectionResult(recognized=False, distance=1.0)

# # # #     # ── Lifecycle ─────────────────────────────────────────────────────────────

# # # #     async def reset(self) -> None:
# # # #         self._state = State.IDLE
# # # #         if self._task and not self._task.done():
# # # #             self._task.cancel()
# # # #             try:
# # # #                 await self._task
# # # #             except asyncio.CancelledError:
# # # #                 pass

# # # #     @property
# # # #     def state(self) -> State:
# # # #         return self._state

# # # # pi4/control/presence_detector.py
# # # """
# # # THIẾT KẾ MỚI - Ổn định, đúng logic, broadcast trạng thái lên Dashboard.

# # # LUỒNG:
# # #   PIR trigger
# # #     → WATCH  (5s) — tìm mặt, broadcast face_scan_start
# # #     → STABILIZE (1.5s) — chờ đứng yên
# # #     → SCAN (max 5 lần) — nhận diện
# # #       → Nhận ra → mở cửa, broadcast face_recognized
# # #       → Không nhận ra → cảnh báo → alarm sau 5 lần
# # #     → broadcast face_scan_end khi kết thúc

# # # KEY FIXES:
# # #   - _ensure_dlib_compatible(): np.ascontiguousarray(img, dtype=np.uint8)
# # #     trước mọi lần gọi dlib để tránh "Unsupported image type"
# # #   - _recog_sync(): đọc từ known_faces.pkl (không nhầm JSON format của backend)
# # #   - broadcast_event(): gửi face_scan_start/end để Dashboard hiển thị live stream
# # # """
# # # from __future__ import annotations

# # # import asyncio
# # # import time
# # # from dataclasses import dataclass
# # # from enum import Enum, auto
# # # from typing import Optional, Callable

# # # import cv2
# # # import numpy as np
# # # import face_recognition

# # # from logging_module.event_logger import log_app
# # # from vision.camera_manager import CameraManager
# # # from recognition.face_encoder import (
# # #     load_known_faces,
# # #     encode_face,
# # #     compare_faces,
# # #     _ensure_dlib_compatible,
# # # )

# # # # ── Tham số ────────────────────────────────────────────────────────────────────
# # # WATCH_DURATION     = 5.0   # tối đa 5s để tìm mặt
# # # STABILIZE_DURATION = 1.5   # chờ đứng yên
# # # SCAN_INTERVAL      = 0.7   # nghỉ giữa các lần scan
# # # MAX_SCAN_RETRIES   = 5     # quét tối đa 5 lần
# # # MIN_FACE_AREA      = 6000  # diện tích pixel tối thiểu
# # # MAX_FACE_MOVEMENT  = 60    # pixel di chuyển tối đa (đứng yên)


# # # class State(Enum):
# # #     IDLE      = auto()
# # #     WATCH     = auto()
# # #     STABILIZE = auto()
# # #     SCANNING  = auto()
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
# # #     ):
# # #         self._camera        = camera
# # #         self._on_recognized = on_recognized
# # #         self._on_unknown    = on_unknown
# # #         self._on_alarm      = on_alarm
# # #         # Optional: async fn(event_type, data_dict) to broadcast via WebSocket
# # #         self._broadcast     = broadcast_fn
# # #         self._state         = State.IDLE
# # #         self._task: Optional[asyncio.Task] = None

# # #     # ── Entry point ────────────────────────────────────────────────────────────

# # #     async def on_pir_triggered(self) -> None:
# # #         if self._state != State.IDLE:
# # #             return
# # #         log_app("info", "[DETECTOR] PIR triggered → WATCH")
# # #         self._state = State.WATCH
# # #         self._task  = asyncio.create_task(self._main_loop())

# # #     # ── Main loop ──────────────────────────────────────────────────────────────

# # #     async def _main_loop(self) -> None:
# # #         try:
# # #             # Notify Dashboard: scanning started → show live stream
# # #             await self._emit("face_scan_start", {"state": "watch"})

# # #             face_box = await self._watch_phase()
# # #             if not face_box:
# # #                 log_app("info", "[DETECTOR] No face in WATCH → IDLE")
# # #                 await self._emit("face_scan_end", {"reason": "no_face_in_watch"})
# # #                 await self.reset()
# # #                 return

# # #             stable = await self._stabilize_phase(face_box)
# # #             if not stable:
# # #                 log_app("info", "[DETECTOR] Not stable → IDLE")
# # #                 await self._emit("face_scan_end", {"reason": "not_stable"})
# # #                 await self.reset()
# # #                 return

# # #             self._state = State.SCANNING
# # #             await self._scan_phase()

# # #         except asyncio.CancelledError:
# # #             pass
# # #         except Exception as exc:
# # #             log_app("error", f"[DETECTOR] Main loop error: {exc}")
# # #             await self._emit("face_scan_end", {"reason": "error"})
# # #             await self.reset()

# # #     # ── WATCH ──────────────────────────────────────────────────────────────────

# # #     async def _watch_phase(self) -> Optional[tuple]:
# # #         start       = time.monotonic()
# # #         consecutive = 0
# # #         while time.monotonic() - start < WATCH_DURATION:
# # #             frame = await self._camera.capture_frame()
# # #             box   = await self._detect_face_box(frame)
# # #             if box:
# # #                 consecutive += 1
# # #                 if consecutive >= 2:
# # #                     return box
# # #             else:
# # #                 consecutive = 0
# # #             await asyncio.sleep(0.2)
# # #         return None

# # #     # ── STABILIZE ──────────────────────────────────────────────────────────────

# # #     async def _stabilize_phase(self, last_box: tuple) -> bool:
# # #         self._state  = State.STABILIZE
# # #         start        = time.monotonic()
# # #         stable_count = 0
# # #         prev_box     = last_box

# # #         while time.monotonic() - start < STABILIZE_DURATION:
# # #             frame    = await self._camera.capture_frame()
# # #             curr_box = await self._detect_face_box(frame)
# # #             if curr_box:
# # #                 top, right, bottom, left = curr_box
# # #                 area     = abs((bottom - top) * (right - left))
# # #                 prev_cx  = (prev_box[3] + prev_box[1]) / 2
# # #                 curr_cx  = (left + right) / 2
# # #                 movement = abs(curr_cx - prev_cx)
# # #                 if area >= MIN_FACE_AREA and movement <= MAX_FACE_MOVEMENT:
# # #                     stable_count += 1
# # #                     if stable_count >= 3:
# # #                         return True
# # #                 else:
# # #                     stable_count = 0
# # #                 prev_box = curr_box
# # #             await asyncio.sleep(0.2)
# # #         return False

# # #     # ── SCAN ───────────────────────────────────────────────────────────────────

# # #     async def _scan_phase(self) -> None:
# # #         for i in range(1, MAX_SCAN_RETRIES + 1):
# # #             log_app("info", f"[SCAN] Attempt {i}/{MAX_SCAN_RETRIES}")
# # #             await self._emit("face_scan_start", {"state": "scanning", "attempt": i})

# # #             best_frame = await self._get_sharpest_frame(n=3)
# # #             if best_frame is None:
# # #                 await asyncio.sleep(SCAN_INTERVAL)
# # #                 continue

# # #             result = await self._recognize(best_frame)

# # #             if result.recognized:
# # #                 log_app("info", f"[SCAN] GRANTED: {result.name} dist={result.distance:.4f}")
# # #                 self._state = State.GRANTED
# # #                 await self._emit("face_recognized", {
# # #                     "name":       result.name,
# # #                     "confidence": round(result.confidence, 4),
# # #                 })
# # #                 await self._on_recognized(result)
# # #                 await asyncio.sleep(5)   # cooldown while person enters
# # #                 await self._emit("face_scan_end", {"reason": "granted"})
# # #                 await self.reset()
# # #                 return

# # #             log_app("info", f"[SCAN] UNKNOWN dist={result.distance:.4f}")
# # #             await self._on_unknown(result)
# # #             if i < MAX_SCAN_RETRIES:
# # #                 await asyncio.sleep(SCAN_INTERVAL)

# # #         log_app("warning", "[SCAN] DENIED after max retries → alarm")
# # #         self._state = State.DENIED
# # #         await self._emit("face_scan_end", {"reason": "denied"})
# # #         await self._on_alarm()
# # #         await asyncio.sleep(3)
# # #         await self.reset()

# # #     # ── Helpers ────────────────────────────────────────────────────────────────

# # #     async def _emit(self, event_type: str, data: dict) -> None:
# # #         """Broadcast event to Dashboard via WebSocket (if broadcast_fn provided)."""
# # #         if self._broadcast:
# # #             try:
# # #                 await self._broadcast(event_type, data)
# # #             except Exception as exc:
# # #                 log_app("debug", f"[DETECTOR] broadcast failed: {exc}")

# # #     async def _detect_face_box(
# # #         self, frame: Optional[np.ndarray]
# # #     ) -> Optional[tuple]:
# # #         if frame is None:
# # #             return None
# # #         loop = asyncio.get_running_loop()
# # #         return await loop.run_in_executor(None, self._detect_sync, frame)

# # #     def _detect_sync(self, frame: np.ndarray) -> Optional[tuple]:
# # #         try:
# # #             # FIX: ensure dlib-compatible array
# # #             img  = _ensure_dlib_compatible(frame)
# # #             boxes = face_recognition.face_locations(
# # #                 img, model="hog", number_of_times_to_upsample=1
# # #             )
# # #             return boxes[0] if boxes else None
# # #         except Exception as exc:
# # #             log_app("debug", f"_detect_sync error: {exc}")
# # #             return None

# # #     async def _get_sharpest_frame(self, n: int = 3) -> Optional[np.ndarray]:
# # #         """Select the sharpest frame (highest Laplacian variance) from n frames."""
# # #         candidates = []
# # #         for _ in range(n):
# # #             frame = await self._camera.capture_frame()
# # #             if frame is not None:
# # #                 gray      = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
# # #                 sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
# # #                 candidates.append((sharpness, frame))
# # #             await asyncio.sleep(0.1)
# # #         if not candidates:
# # #             return None
# # #         return max(candidates, key=lambda x: x[0])[1]

# # #     async def _recognize(self, frame: np.ndarray) -> DetectionResult:
# # #         loop = asyncio.get_running_loop()
# # #         return await loop.run_in_executor(None, self._recog_sync, frame)

# # #     def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
# # #         """
# # #         Blocking recognition in thread pool.
# # #         Reads from known_faces.pkl RAM cache.
# # #         """
# # #         try:
# # #             known = load_known_faces()
# # #             if not known:
# # #                 log_app("warning", "No enrolled faces — recognition skipped")
# # #                 return DetectionResult(recognized=False, distance=1.0)

# # #             encodings = encode_face(frame)   # uses _ensure_dlib_compatible internally
# # #             if not encodings:
# # #                 return DetectionResult(recognized=False, distance=1.0)

# # #             name, distance = compare_faces(encodings[0], known)
# # #             confidence     = max(0.0, 1.0 - distance)

# # #             return DetectionResult(
# # #                 recognized=(name is not None),
# # #                 name=name,
# # #                 distance=distance,
# # #                 confidence=confidence,
# # #             )
# # #         except Exception as exc:
# # #             log_app("error", f"_recog_sync error: {exc}")
# # #             return DetectionResult(recognized=False, distance=1.0)

# # #     async def reset(self) -> None:
# # #         self._state = State.IDLE
# # #         if self._task and not self._task.done():
# # #             self._task.cancel()
# # #             try:
# # #                 await self._task
# # #             except asyncio.CancelledError:
# # #                 pass

# # #     @property
# # #     def state(self) -> State:
# # #         return self._state

# # # pi4/control/presence_detector.py
# # """
# # THIẾT KẾ MỚI - Ổn định, đúng logic, broadcast trạng thái lên Dashboard.

# # LUỒNG:
# #   PIR trigger
# #     → WATCH  (5s) — tìm mặt, broadcast face_scan_start
# #     → STABILIZE (1.5s) — chờ đứng yên
# #     → SCAN (max 5 lần) — nhận diện
# #       → Nhận ra → mở cửa, broadcast face_recognized
# #       → Không nhận ra → cảnh báo → alarm sau 5 lần
# #     → broadcast face_scan_end khi kết thúc

# # KEY FIXES:
# #   - _ensure_dlib_compatible(): np.ascontiguousarray(img, dtype=np.uint8)
# #     trước mọi lần gọi dlib để tránh "Unsupported image type"
# #   - _recog_sync(): đọc từ known_faces.pkl (không nhầm JSON format của backend)
# #   - broadcast_event(): gửi face_scan_start/end để Dashboard hiển thị live stream
# # """
# # from __future__ import annotations

# # import asyncio
# # import time
# # from dataclasses import dataclass
# # from enum import Enum, auto
# # from typing import Optional, Callable

# # import cv2
# # import numpy as np
# # import face_recognition

# # from logging_module.event_logger import log_app
# # from vision.camera_manager import CameraManager
# # from recognition.face_encoder import (
# #     load_known_faces,
# #     encode_face,
# #     compare_faces,
# #     _ensure_dlib_compatible,
# # )

# # # ── Tham số ────────────────────────────────────────────────────────────────────
# # WATCH_DURATION     = 5.0   # tối đa 5s để tìm mặt
# # STABILIZE_DURATION = 1.5   # chờ đứng yên
# # SCAN_INTERVAL      = 0.7   # nghỉ giữa các lần scan
# # MAX_SCAN_RETRIES   = 5     # quét tối đa 5 lần
# # MIN_FACE_AREA      = 6000  # diện tích pixel tối thiểu
# # MAX_FACE_MOVEMENT  = 60    # pixel di chuyển tối đa (đứng yên)


# # class State(Enum):
# #     IDLE      = auto()
# #     WATCH     = auto()
# #     STABILIZE = auto()
# #     SCANNING  = auto()
# #     GRANTED   = auto()
# #     DENIED    = auto()


# # @dataclass
# # class DetectionResult:
# #     recognized: bool
# #     name:       Optional[str] = None
# #     distance:   float         = 1.0
# #     confidence: float         = 0.0


# # class PresenceDetector:
# #     def __init__(
# #         self,
# #         camera:        CameraManager,
# #         on_recognized: Callable,
# #         on_unknown:    Callable,
# #         on_alarm:      Callable,
# #         broadcast_fn:  Optional[Callable] = None,
# #     ):
# #         self._camera        = camera
# #         self._on_recognized = on_recognized
# #         self._on_unknown    = on_unknown
# #         self._on_alarm      = on_alarm
# #         # Optional: async fn(event_type, data_dict) to broadcast via WebSocket
# #         self._broadcast     = broadcast_fn
# #         self._state         = State.IDLE
# #         self._task: Optional[asyncio.Task] = None

# #     # ── Entry point ────────────────────────────────────────────────────────────

# #     async def on_pir_triggered(self) -> None:
# #         if self._state != State.IDLE:
# #             return
# #         log_app("info", "[DETECTOR] PIR triggered → WATCH")
# #         self._state = State.WATCH
# #         self._task  = asyncio.create_task(self._main_loop())

# #     # ── Main loop ──────────────────────────────────────────────────────────────

# #     async def _main_loop(self) -> None:
# #         try:
# #             # Notify Dashboard: scanning started → show live stream
# #             await self._emit("face_scan_start", {"state": "watch"})

# #             face_box = await self._watch_phase()
# #             if not face_box:
# #                 log_app("info", "[DETECTOR] No face in WATCH → IDLE")
# #                 await self._emit("face_scan_end", {"reason": "no_face_in_watch"})
# #                 await self.reset()
# #                 return

# #             stable = await self._stabilize_phase(face_box)
# #             if not stable:
# #                 log_app("info", "[DETECTOR] Not stable → IDLE")
# #                 await self._emit("face_scan_end", {"reason": "not_stable"})
# #                 await self.reset()
# #                 return

# #             self._state = State.SCANNING
# #             await self._scan_phase()

# #         except asyncio.CancelledError:
# #             pass
# #         except Exception as exc:
# #             log_app("error", f"[DETECTOR] Main loop error: {exc}")
# #             await self._emit("face_scan_end", {"reason": "error"})
# #             await self.reset()

# #     # ── WATCH ──────────────────────────────────────────────────────────────────

# #     async def _watch_phase(self) -> Optional[tuple]:
# #         start       = time.monotonic()
# #         consecutive = 0
# #         while time.monotonic() - start < WATCH_DURATION:
# #             frame = await self._camera.capture_frame()
# #             box   = await self._detect_face_box(frame)
# #             if box:
# #                 consecutive += 1
# #                 if consecutive >= 2:
# #                     return box
# #             else:
# #                 consecutive = 0
# #             await asyncio.sleep(0.2)
# #         return None

# #     # ── STABILIZE ──────────────────────────────────────────────────────────────

# #     async def _stabilize_phase(self, last_box: tuple) -> bool:
# #         self._state  = State.STABILIZE
# #         start        = time.monotonic()
# #         stable_count = 0
# #         prev_box     = last_box

# #         while time.monotonic() - start < STABILIZE_DURATION:
# #             frame    = await self._camera.capture_frame()
# #             curr_box = await self._detect_face_box(frame)
# #             if curr_box:
# #                 top, right, bottom, left = curr_box
# #                 area     = abs((bottom - top) * (right - left))
# #                 prev_cx  = (prev_box[3] + prev_box[1]) / 2
# #                 curr_cx  = (left + right) / 2
# #                 movement = abs(curr_cx - prev_cx)
# #                 if area >= MIN_FACE_AREA and movement <= MAX_FACE_MOVEMENT:
# #                     stable_count += 1
# #                     if stable_count >= 3:
# #                         return True
# #                 else:
# #                     stable_count = 0
# #                 prev_box = curr_box
# #             await asyncio.sleep(0.2)
# #         return False

# #     # ── SCAN ───────────────────────────────────────────────────────────────────

# #     async def _scan_phase(self) -> None:
# #         for i in range(1, MAX_SCAN_RETRIES + 1):
# #             log_app("info", f"[SCAN] Attempt {i}/{MAX_SCAN_RETRIES}")
# #             await self._emit("face_scan_start", {"state": "scanning", "attempt": i})

# #             best_frame = await self._get_sharpest_frame(n=3)
# #             if best_frame is None:
# #                 await asyncio.sleep(SCAN_INTERVAL)
# #                 continue

# #             result = await self._recognize(best_frame)

# #             if result.recognized:
# #                 log_app("info", f"[SCAN] GRANTED: {result.name} dist={result.distance:.4f}")
# #                 self._state = State.GRANTED
# #                 await self._emit("face_recognized", {
# #                     "name":       result.name,
# #                     "confidence": round(result.confidence, 4),
# #                 })
# #                 await self._on_recognized(result)
# #                 await asyncio.sleep(5)   # cooldown while person enters
# #                 await self._emit("face_scan_end", {"reason": "granted"})
# #                 await self.reset()
# #                 return

# #             log_app("info", f"[SCAN] UNKNOWN dist={result.distance:.4f}")
# #             await self._on_unknown(result)
# #             if i < MAX_SCAN_RETRIES:
# #                 await asyncio.sleep(SCAN_INTERVAL)

# #         log_app("warning", "[SCAN] DENIED after max retries → alarm")
# #         self._state = State.DENIED
# #         await self._emit("face_scan_end", {"reason": "denied"})
# #         await self._on_alarm()
# #         await asyncio.sleep(3)
# #         await self.reset()

# #     # ── Helpers ────────────────────────────────────────────────────────────────

# #     async def _emit(self, event_type: str, data: dict) -> None:
# #         """Broadcast event to Dashboard via WebSocket (if broadcast_fn provided)."""
# #         if self._broadcast:
# #             try:
# #                 await self._broadcast(event_type, data)
# #             except Exception as exc:
# #                 log_app("debug", f"[DETECTOR] broadcast failed: {exc}")

# #     async def _detect_face_box(
# #         self, frame: Optional[np.ndarray]
# #     ) -> Optional[tuple]:
# #         if frame is None:
# #             return None
# #         loop = asyncio.get_running_loop()
# #         return await loop.run_in_executor(None, self._detect_sync, frame)

# #     def _detect_sync(self, frame: np.ndarray) -> Optional[tuple]:
# #         try:
# #             # FIX: ensure dlib-compatible array
# #             img  = _ensure_dlib_compatible(frame)
# #             boxes = face_recognition.face_locations(
# #                 img, model="hog", number_of_times_to_upsample=1
# #             )
# #             return boxes[0] if boxes else None
# #         except Exception as exc:
# #             log_app("debug", f"_detect_sync error: {exc}")
# #             return None

# #     async def _get_sharpest_frame(self, n: int = 3) -> Optional[np.ndarray]:
# #         """Select the sharpest frame (highest Laplacian variance) from n frames."""
# #         candidates = []
# #         for _ in range(n):
# #             frame = await self._camera.capture_frame()
# #             if frame is not None:
# #                 gray      = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
# #                 sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
# #                 candidates.append((sharpness, frame))
# #             await asyncio.sleep(0.1)
# #         if not candidates:
# #             return None
# #         return max(candidates, key=lambda x: x[0])[1]

# #     async def _recognize(self, frame: np.ndarray) -> DetectionResult:
# #         loop = asyncio.get_running_loop()
# #         return await loop.run_in_executor(None, self._recog_sync, frame)

# #     def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
# #         """
# #         Blocking recognition in thread pool.
# #         Reads from known_faces.pkl RAM cache.
# #         """
# #         try:
# #             known = load_known_faces()
# #             if not known:
# #                 log_app("warning", "No enrolled faces — recognition skipped")
# #                 return DetectionResult(recognized=False, distance=1.0)

# #             encodings = encode_face(frame)   # uses _ensure_dlib_compatible internally
# #             if not encodings:
# #                 return DetectionResult(recognized=False, distance=1.0)

# #             name, distance = compare_faces(encodings[0], known)
# #             confidence     = max(0.0, 1.0 - distance)

# #             return DetectionResult(
# #                 recognized=(name is not None),
# #                 name=name,
# #                 distance=distance,
# #                 confidence=confidence,
# #             )
# #         except Exception as exc:
# #             log_app("error", f"_recog_sync error: {exc}")
# #             return DetectionResult(recognized=False, distance=1.0)

# #     async def reset(self) -> None:
# #         self._state = State.IDLE
# #         if self._task and not self._task.done():
# #             self._task.cancel()
# #             try:
# #                 await self._task
# #             except asyncio.CancelledError:
# #                 pass

# #     @property
# #     def state(self) -> State:
# #         return self._state




# # pi4/control/presence_detector.py
# from __future__ import annotations

# import asyncio
# import time
# import base64
# from dataclasses import dataclass
# from datetime import datetime
# from enum import Enum, auto
# from typing import Optional, Callable

# import cv2
# import numpy as np
# import face_recognition
# import aiohttp

# from config.settings import settings
# from logging_module.event_logger import log_app
# from vision.camera_manager import CameraManager
# from recognition.face_encoder import (
#     load_known_faces,
#     encode_face,
#     compare_faces,
#     _ensure_dlib_compatible,
# )

# # ── Tham số Tuning ────────────────────────────────────────────────────────────
# WATCH_DURATION     = 5.0   # Tối đa 5s để tìm mặt
# STABILIZE_DURATION = 1.5   # Chờ đứng yên 1.5s
# SCAN_INTERVAL      = 0.7   # Nghỉ giữa các lần quét
# MAX_SCAN_RETRIES   = 5     # Quét mặt tối đa 5 lần
# MIN_FACE_AREA      = 6000  # Diện tích mặt tối thiểu
# MAX_FACE_MOVEMENT  = 60    # Pixel di chuyển tối đa (đứng yên)
# FRAME_BROADCAST_INTERVAL = 0.4 # Giảm tải băng thông stream

# class State(Enum):
#     IDLE      = auto()
#     WATCH     = auto()
#     STABILIZE = auto()
#     SCANNING  = auto()
#     GRANTED   = auto()
#     DENIED    = auto()

# @dataclass
# class DetectionResult:
#     recognized: bool
#     name:       Optional[str] = None
#     distance:   float         = 1.0
#     confidence: float         = 0.0

# class PresenceDetector:
#     def __init__(
#         self,
#         camera:        CameraManager,
#         on_recognized: Callable, # Thường là DoorController.unlock
#         on_unknown:    Callable, # Ghi log unknown
#         on_alarm:      Callable, # Thường là AlarmController.trigger
#         broadcast_fn:  Optional[Callable] = None,
#         uart_send_fn:  Optional[Callable] = None, # Hàm gửi lệnh xuống STM32
#     ):
#         self._camera         = camera
#         self._on_recognized = on_recognized
#         self._on_unknown     = on_unknown
#         self._on_alarm       = on_alarm
#         self._broadcast      = broadcast_fn
#         self._uart_send      = uart_send_fn
#         self._state          = State.IDLE
#         self._task: Optional[asyncio.Task] = None

#     async def on_pir_triggered(self) -> None:
#         if self._state != State.IDLE: return
#         log_app("info", "[DETECTOR] PIR triggered → WATCH")
#         self._state = State.WATCH
#         self._task  = asyncio.create_task(self._main_loop())

#     async def _main_loop(self) -> None:
#         try:
#             await self._emit("face_scan_start", {"state": "watch"})

#             face_box = await self._watch_phase()
#             if not face_box:
#                 await self._emit("face_scan_end", {"reason": "no_face"})
#                 await self.reset(); return

#             stable = await self._stabilize_phase(face_box)
#             if not stable:
#                 await self._emit("face_scan_end", {"reason": "unstable"})
#                 await self.reset(); return

#             self._state = State.SCANNING
#             await self._scan_phase()

#         except asyncio.CancelledError:
#             pass
#         except Exception as exc:
#             log_app("error", f"[DETECTOR] Loop error: {exc}")
#             await self.reset()

#     async def _watch_phase(self) -> Optional[tuple]:
#         start = time.monotonic()
#         consecutive = 0
#         last_broadcast = 0.0
#         while time.monotonic() - start < WATCH_DURATION:
#             frame = await self._camera.capture_frame()

#             now = time.monotonic()
#             if frame is not None and (now - last_broadcast) >= FRAME_BROADCAST_INTERVAL:
#                 await self._broadcast_frame_async(frame, "WATCH")
#                 last_broadcast = now

#             box = await self._detect_face_box(frame)
#             if box:
#                 consecutive += 1
#                 if consecutive >= 2: return box
#             else: consecutive = 0
#             await asyncio.sleep(0.2)
#         return None

#     async def _stabilize_phase(self, last_box: tuple) -> bool:
#         self._state = State.STABILIZE
#         start = time.monotonic()
#         stable_count = 0
#         prev_box = last_box
#         last_broadcast = 0.0
#         while time.monotonic() - start < STABILIZE_DURATION:
#             frame = await self._camera.capture_frame()

#             now = time.monotonic()
#             if frame is not None and (now - last_broadcast) >= FRAME_BROADCAST_INTERVAL:
#                 await self._broadcast_frame_async(frame, "STABILIZE")
#                 last_broadcast = now

#             curr_box = await self._detect_face_box(frame)
#             if curr_box:
#                 top, right, bottom, left = curr_box
#                 area = abs((bottom - top) * (right - left))
#                 movement = abs(((left + right) / 2) - ((prev_box[3] + prev_box[1]) / 2))
#                 if area >= MIN_FACE_AREA and movement <= MAX_FACE_MOVEMENT:
#                     stable_count += 1
#                     if stable_count >= 3: return True
#                 else: stable_count = 0
#                 prev_box = curr_box
#             await asyncio.sleep(0.2)
#         return False

#     async def _scan_phase(self) -> None:
#         for i in range(1, MAX_SCAN_RETRIES + 1):
#             log_app("info", f"[SCAN] Attempt {i}/{MAX_SCAN_RETRIES}")
#             best_frame = await self._get_sharpest_frame(n=3)
#             if best_frame is None: continue

#             await self._broadcast_frame_async(best_frame, "SCANNING", attempt=i)
#             result = await self._recognize(best_frame)

#             if result.recognized:
#                 log_app("info", f"[SCAN] SUCCESS: {result.name}")
#                 self._state = State.GRANTED
#                 await self._emit("face_recognized", {"name": result.name})
#                 await self._on_recognized(result)
#                 await asyncio.sleep(5)
#                 await self.reset(); return

#             await self._on_unknown(result)
#             await asyncio.sleep(SCAN_INTERVAL)

#         # ── XỬ LÝ KHI THẤT BẠI 5 LẦN (SECURITY BREACH) ──────────────────────
#         log_app("warning", "[SCAN] DENIED -> Intruder Warning & Enable Keypad")
#         self._state = State.DENIED

#         # 1. Gửi cảnh báo về Web Dashboard
#         await self._emit("alarm_intruder_warning", {"detail": "Face recognition failed 5 times"})

#         # 2. Kích hoạt chế độ nhập PIN trên STM32
#         if self._uart_send:
#             await self._uart_send("CMD_ENABLE_KEYPAD\n")
#             log_app("info", "[DETECTOR] UART -> CMD_ENABLE_KEYPAD sent")

#         await self._on_alarm() # Gọi controller xử lý logic báo động chung
#         await asyncio.sleep(3)
#         await self.reset()

#     # ── Helpers & Async Comms ──────────────────────────────────────────────────

#     async def _broadcast_frame_async(self, frame, state, attempt=0):
#         """Gửi frame b64 lên Backend để Dashboard hiển thị live stream"""
#         try:
#             _, buf = cv2.imencode(".jpg", frame[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 50])
#             frame_b64 = base64.b64encode(buf).decode("ascii")
#             await self._emit("scan_frame", {
#                 "frame_b64": frame_b64,
#                 "scan_state": state,
#                 "attempt": attempt
#             })
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

#     async def _get_sharpest_frame(self, n: int = 3) -> Optional[np.ndarray]:
#         candidates = []
#         for _ in range(n):
#             f = await self._camera.capture_frame()
#             if f is not None:
#                 lap = cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
#                 candidates.append((lap, f))
#             await asyncio.sleep(0.1)
#         return max(candidates, key=lambda x: x[0])[1] if candidates else None

#     async def _recognize(self, frame: np.ndarray) -> DetectionResult:
#         loop = asyncio.get_running_loop()
#         return await loop.run_in_executor(None, self._recog_sync, frame)

#     def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
#         try:
#             known = load_known_faces()
#             encs = encode_face(frame)
#             if not known or not encs: return DetectionResult(False)
#             name, dist = compare_faces(encs[0], known)
#             return DetectionResult(name is not None, name, dist, max(0.0, 1.0 - dist))
#         except: return DetectionResult(False)

#     async def reset(self) -> None:
#         self._state = State.IDLE
#         if self._task and not self._task.done():
#             self._task.cancel()
# @property
#     def state(self):
#         return self._state



# pi4/control/presence_detector.py
from __future__ import annotations

import asyncio
import time
import base64
import cv2
import numpy as np
import face_recognition
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Callable

from config.settings import settings
from logging_module.event_logger import log_app
from vision.camera_manager import CameraManager
from recognition.face_encoder import (
    load_known_faces,
    encode_face,
    compare_faces,
    _ensure_dlib_compatible,
)

# ── Tham số Tuning ────────────────────────────────────────────────────────────
WATCH_DURATION     = 5.0   # Tối đa 5s để tìm mặt
STABILIZE_DURATION = 1.5   # Chờ đứng yên 1.5s
SCAN_INTERVAL      = 0.7   # Nghỉ giữa các lần quét
MAX_SCAN_RETRIES   = 5     # Quét mặt tối đa 5 lần
MIN_FACE_AREA      = 3000  # Diện tích mặt tối thiểu
MAX_FACE_MOVEMENT  = 150    # Pixel di chuyển tối đa (đứng yên)
FRAME_BROADCAST_INTERVAL = 0.4

class State(Enum):
    IDLE      = auto()
    WATCH     = auto()
    STABILIZE = auto()
    SCANNING  = auto()
    GRANTED   = auto()
    DENIED    = auto()

@dataclass
class DetectionResult:
    recognized: bool
    name:       Optional[str] = None
    distance:   float         = 1.0
    confidence: float         = 0.0

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
        """Trả về trạng thái hiện tại (Dùng cho file Test)"""
        return self._state

    async def on_pir_triggered(self) -> None:
        if self._state != State.IDLE: return
        log_app("info", "[DETECTOR] PIR triggered → WATCH")
        self._state = State.WATCH
        self._task  = asyncio.create_task(self._main_loop())

    async def _main_loop(self) -> None:
        try:
            await self._emit("face_scan_start", {"state": "watch"})
            face_box = await self._watch_phase()
            if not face_box:
                await self._emit("face_scan_end", {"reason": "no_face"})
                await self.reset(); return

            stable = await self._stabilize_phase(face_box)
            if not stable:
                await self._emit("face_scan_end", {"reason": "unstable"})
                await self.reset(); return

            self._state = State.SCANNING
            await self._scan_phase()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log_app("error", f"[DETECTOR] Loop error: {exc}")
            await self.reset()

    async def _watch_phase(self) -> Optional[tuple]:
        start = time.monotonic()
        consecutive = 0
        last_broadcast = 0.0
        while time.monotonic() - start < WATCH_DURATION:
            frame = await self._camera.capture_frame()
            if frame is not None and (time.monotonic() - last_broadcast) >= FRAME_BROADCAST_INTERVAL:
                await self._broadcast_frame_async(frame, "WATCH")
                last_broadcast = time.monotonic()
            box = await self._detect_face_box(frame)
            if box:
                consecutive += 1
                if consecutive >= 2: return box
            else: consecutive = 0
            await asyncio.sleep(0.2)
        return None

    async def _stabilize_phase(self, last_box: tuple) -> bool:
        self._state = State.STABILIZE
        start = time.monotonic()
        stable_count = 0
        prev_box = last_box
        last_broadcast = 0.0
        while time.monotonic() - start < STABILIZE_DURATION:
            frame = await self._camera.capture_frame()
            if frame is not None and (time.monotonic() - last_broadcast) >= FRAME_BROADCAST_INTERVAL:
                await self._broadcast_frame_async(frame, "STABILIZE")
                last_broadcast = time.monotonic()
            curr_box = await self._detect_face_box(frame)
            if curr_box:
                top, right, bottom, left = curr_box
                area = abs((bottom - top) * (right - left))
                movement = abs(((left + right) / 2) - ((prev_box[3] + prev_box[1]) / 2))
                if area >= MIN_FACE_AREA and movement <= MAX_FACE_MOVEMENT:
                    stable_count += 1
                    if stable_count >= 3: return True
                else: stable_count = 0
                prev_box = curr_box
            await asyncio.sleep(0.2)
        return False

    async def _scan_phase(self) -> None:
        for i in range(1, MAX_SCAN_RETRIES + 1):
            log_app("info", f"[SCAN] Attempt {i}/{MAX_SCAN_RETRIES}")
            best_frame = await self._get_sharpest_frame(n=3)
            if best_frame is None: continue
            await self._broadcast_frame_async(best_frame, "SCANNING", attempt=i)
            result = await self._recognize(best_frame)
            if result.recognized:
                log_app("info", f"[SCAN] SUCCESS: {result.name}")
                self._state = State.GRANTED
                await self._emit("face_recognized", {"name": result.name})
                await self._on_recognized(result)
                await asyncio.sleep(5)
                await self.reset(); return
            await self._on_unknown(result)
            await asyncio.sleep(SCAN_INTERVAL)

        log_app("warning", "[SCAN] DENIED -> Intruder Warning & Enable Keypad")
        self._state = State.DENIED
        await self._emit("alarm_intruder_warning", {"detail": "Face recognition failed 5 times"})
        if self._uart_send:
            await self._uart_send("CMD_ENABLE_KEYPAD\n")
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

    async def _get_sharpest_frame(self, n: int = 3) -> Optional[np.ndarray]:
        candidates = []
        for _ in range(n):
            f = await self._camera.capture_frame()
            if f is not None:
                lap = cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
                candidates.append((lap, f))
            await asyncio.sleep(0.1)
        return max(candidates, key=lambda x: x[0])[1] if candidates else None

    async def _recognize(self, frame: np.ndarray) -> DetectionResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._recog_sync, frame)

    def _recog_sync(self, frame: np.ndarray) -> DetectionResult:
        try:
            known = load_known_faces()
            encs = encode_face(frame)
            if not known or not encs: return DetectionResult(False)
            name, dist = compare_faces(encs[0], known)
            return DetectionResult(name is not None, name, dist, max(0.0, 1.0 - dist))
        except: return DetectionResult(False)

    async def reset(self) -> None:
        self._state = State.IDLE
        if self._task and not self._task.done():
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass

import asyncio
import time
import cv2
import numpy as np
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable
import face_recognition

from config.settings import settings
from logging_module.event_logger import log_app
from vision.camera_manager import CameraManager

# ── CẤU HÌNH THÔNG SỐ ──────────────────────────────────────────────────
WATCH_DURATION     = 5.0    # Chờ xem người đó có đứng lại không
STABILIZE_DURATION = 1.5    # Chờ đứng yên để lấy ảnh nét
SCAN_INTERVAL      = 0.7    # Khoảng nghỉ giữa 5 lần quét (không quá nhanh/chậm)
MAX_SCAN_RETRIES   = 5      # Quét tối đa 5 lần
MIN_FACE_AREA      = 9000   # Diện tích mặt đủ to (đang đứng gần cửa)
MAX_FACE_MOVEMENT  = 50     # Độ xê dịch tâm mặt tối đa giữa các frame (đứng yên)

class State(Enum):
    IDLE      = auto()
    WATCH     = auto()
    STABILIZE = auto()
    SCANNING  = auto()
    GRANTED   = auto()
    DENIED    = auto()

@dataclass
class DetectionResult:
    recognized:  bool
    resident_id: Optional[int] = None
    name:        Optional[str] = None
    confidence:  float = 0.0

class PresenceDetector:
    def __init__(self, camera, on_recognized, on_unknown, on_alarm):
        self._camera = camera
        self._on_recognized = on_recognized
        self._on_unknown = on_unknown
        self._on_alarm = on_alarm
        self._state = State.IDLE
        self._task = None

    async def on_pir_triggered(self):
        if self._state != State.IDLE: return
        log_app("info", "[DETECTOR] Có chuyển động -> WATCH")
        self._state = State.WATCH
        self._task = asyncio.create_task(self._main_loop())

    async def _main_loop(self):
        try:
            # BƯỚC 1: WATCH - Tìm mặt trong 5s
            face_box = await self._watch_phase()
            if not face_box:
                await self.reset(); return

            # BƯỚC 2: STABILIZE - Chờ đứng yên 1.5s
            is_stable = await self._stabilize_phase(face_box)
            if not is_stable:
                await self.reset(); return

            # BƯỚC 3: SCANNING - Quét 5 lần
            self._state = State.SCANNING
            await self._scan_phase()

        except Exception as e:
            log_app("error", f"Detector Loop Error: {e}")
            await self.reset()

    async def _watch_phase(self):
        start = time.monotonic()
        count = 0
        while time.monotonic() - start < WATCH_DURATION:
            frame = await self._camera.capture_frame()
            box = await self._detect_box(frame)
            if box:
                count += 1
                if count >= 2: return box
            else: count = 0
            await asyncio.sleep(0.2)
        return None

    async def _stabilize_phase(self, last_box):
        self._state = State.STABILIZE
        start = time.monotonic()
        stable_count = 0
        prev_box = last_box
        while time.monotonic() - start < STABILIZE_DURATION:
            frame = await self._camera.capture_frame()
            curr_box = await self._detect_box(frame)
            if curr_box:
                area = (curr_box[2]-curr_box[0]) * (curr_box[1]-curr_box[3])
                movement = abs(((curr_box[0]+curr_box[2])/2) - ((prev_box[0]+prev_box[2])/2))
                if area > MIN_FACE_AREA and movement < MAX_FACE_MOVEMENT:
                    stable_count += 1
                    if stable_count >= 3: return True
                else: stable_count = 0
                prev_box = curr_box
            await asyncio.sleep(0.2)
        return False

    async def _scan_phase(self):
        for i in range(1, MAX_SCAN_RETRIES + 1):
            log_app("info", f"[SCAN] Thử lần {i}/{MAX_SCAN_RETRIES}")
            frame = await self._camera.capture_frame()
            # Chọn frame nét nhất trong 3 frame nhỏ
            best_frame = await self._get_best_of_n(3)
            result = await self._recognize(best_frame)

            if result.recognized:
                log_app("info", f"[SUCCESS] Chào {result.name}")
                self._state = State.GRANTED
                await self._on_recognized(result)
                await asyncio.sleep(5) # Chờ người ta vào nhà
                await self.reset(); return

            await self._on_unknown(result)
            if i < MAX_SCAN_RETRIES:
                await asyncio.sleep(SCAN_INTERVAL)

        log_app("warn", "[FAILED] Không nhận diện được sau 5 lần")
        self._state = State.DENIED
        await self._on_alarm()
        await asyncio.sleep(3)
        await self.reset()

    async def _detect_box(self, frame):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._detect_sync, frame)

    def _detect_sync(self, frame):
        rgb = frame[:, :, ::-1]
        boxes = face_recognition.face_locations(rgb, model="hog")
        return boxes[0] if boxes else None

    async def _get_best_of_n(self, n):
        frames = []
        for _ in range(n):
            f = await self._camera.capture_frame()
            if f is not None:
                lap = cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
                frames.append((lap, f))
            await asyncio.sleep(0.1)
        return max(frames, key=lambda x: x[0])[1] if frames else None

    async def _recognize(self, frame):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._recog_sync, frame)

    def _recog_sync(self, frame):
        # Giả định bạn đã có logic load encodings từ file json như trước
        import json
        from pathlib import Path
        try:
            with open(settings.encodings_path) as f:
                db = json.load(f)
            known_enc = [item["encoding"] for item in db]
            rgb = frame[:, :, ::-1]
            locs = face_recognition.face_locations(rgb, model="hog")
            if not locs: return DetectionResult(False)
            enc = face_recognition.face_encodings(rgb, locs)[0]
            dists = face_recognition.face_distance(known_enc, enc)
            idx = np.argmin(dists)
            if dists[idx] <= settings.face_tolerance:
                return DetectionResult(True, db[idx]["id"], db[idx]["name"], 1-dists[idx])
        except: pass
        return DetectionResult(False)

    async def reset(self):
        self._state = State.IDLE
        if self._task: self._task.cancel()

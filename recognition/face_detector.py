# recognition/face_detector.py
from __future__ import annotations

import asyncio
import dataclasses
from typing import Optional

from config.settings import settings
from config.constants import FACE_CAPTURE_DELAY

from vision.camera_manager import CameraManager
from vision.frame_processor import preprocess
from vision.snapshot import save_and_stage
from recognition.face_encoder import encode_face, compare_faces, load_known_faces
from logging_module.event_logger import log_app, log_event, EventType


@dataclasses.dataclass
class RecognitionResult:
    success:    bool
    name:       Optional[str]   = None
    distance:   float           = 1.0
    attempts:   int             = 0
    image_path: Optional[str]   = None


async def detect_with_retry(
    camera: CameraManager,
    max_attempts: int | None = None,
    tolerance: float | None  = None,
) -> RecognitionResult:

    # Load thông số cấu hình tự động
    if max_attempts is None:
        max_attempts = settings.max_face_retry
    if tolerance is None:
        tolerance = settings.face_tolerance

    known = load_known_faces()
    if not known:
        log_app("warning", "No known faces enrolled — recognition will always fail")

    best_result = RecognitionResult(success=False, attempts=0, distance=1.0)
    loop = asyncio.get_running_loop()

    for attempt in range(1, max_attempts + 1):
        log_event(EventType.FACE_ATTEMPT, attempt=attempt, max=max_attempts)

        frame = await camera.capture_frame()
        if frame is None:
            await asyncio.sleep(FACE_CAPTURE_DELAY)
            continue

        processed = preprocess(frame)
        if processed is None:
            await asyncio.sleep(FACE_CAPTURE_DELAY)
            continue

        # Chạy thuật toán AI nặng trên ThreadPool
        encodings = await loop.run_in_executor(None, encode_face, processed)

        # -------------------------------------------------------------------
        # CHIẾN THUẬT BURST CAPTURE (GHI LẠI MỌI BẰNG CHỨNG)
        # -------------------------------------------------------------------
        if not encodings:
            log_app("debug", f"No face detected in frame (Attempt {attempt})")
            # Vẫn lưu lại để làm bằng chứng (có thể kẻ gian đang lấy tay che camera)
            await save_and_stage(processed, prefix=f"no_face_attempt_{attempt}")

            best_result.attempts = attempt
            await asyncio.sleep(FACE_CAPTURE_DELAY)
            continue

        name, distance = await loop.run_in_executor(
            None, compare_faces, encodings[0], known, tolerance
        )

        # Cập nhật kết quả tốt nhất (khoảng cách gần nhất)
        if distance < best_result.distance:
            best_result.distance = distance
            best_result.attempts = attempt

        if name is not None:
            # NHẬN DIỆN THÀNH CÔNG -> Lưu ảnh success và mở cửa ngay lập tức
            staged = await save_and_stage(processed, prefix=f"success_{name}")
            best_result.success = True
            best_result.name = name
            best_result.image_path = str(staged) if staged else None

            log_event(
                EventType.FACE_SUCCESS,
                name=name,
                distance=round(distance, 4),
                attempt=attempt,
                image=best_result.image_path,
            )
            return best_result
        else:
            # NHẬN DIỆN THẤT BẠI (Có mặt người nhưng lạ) -> Lưu lại làm bằng chứng
            staged = await save_and_stage(processed, prefix=f"unknown_attempt_{attempt}")
            best_result.image_path = str(staged) if staged else None

            await asyncio.sleep(FACE_CAPTURE_DELAY)

    # =========================================================================
    # KẾT THÚC VÒNG LẶP MÀ VẪN THẤT BẠI (Intruder Alert)
    # =========================================================================
    log_event(
        EventType.FACE_FAILED,
        attempts=max_attempts,
        best_distance=round(best_result.distance, 4),
        image=best_result.image_path, # Gửi kèm bức ảnh cuối cùng cùng với sự kiện lỗi
    )

    best_result.attempts = max_attempts
    return best_result

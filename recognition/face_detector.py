# # recognition/face_detector.py
# from __future__ import annotations

# import asyncio
# import dataclasses
# from typing import Optional

# from config.settings import settings
# from config.constants import FACE_CAPTURE_DELAY

# from vision.camera_manager import CameraManager
# from vision.frame_processor import preprocess
# from vision.snapshot import save_and_stage
# from recognition.face_encoder import encode_face, compare_faces, load_known_faces
# from logging_module.event_logger import log_app, log_event, EventType


# @dataclasses.dataclass
# class RecognitionResult:
#     success:    bool
#     name:       Optional[str]   = None
#     distance:   float           = 1.0
#     attempts:   int             = 0
#     image_path: Optional[str]   = None


# async def detect_with_retry(
#     camera: CameraManager,
#     max_attempts: int | None = None,
#     tolerance: float | None  = None,
# ) -> RecognitionResult:

#     # Load thông số cấu hình tự động
#     if max_attempts is None:
#         max_attempts = settings.max_face_retry
#     if tolerance is None:
#         tolerance = settings.face_tolerance

#     known = load_known_faces()
#     if not known:
#         log_app("warning", "No known faces enrolled — recognition will always fail")

#     best_result = RecognitionResult(success=False, attempts=0, distance=1.0)
#     loop = asyncio.get_running_loop()

#     for attempt in range(1, max_attempts + 1):
#         log_event(EventType.FACE_ATTEMPT, attempt=attempt, max=max_attempts)

#         frame = await camera.capture_frame()
#         if frame is None:
#             await asyncio.sleep(FACE_CAPTURE_DELAY)
#             continue

#         processed = preprocess(frame)
#         if processed is None:
#             await asyncio.sleep(FACE_CAPTURE_DELAY)
#             continue

#         # Chạy thuật toán AI nặng trên ThreadPool
#         encodings = await loop.run_in_executor(None, encode_face, processed)

#         # -------------------------------------------------------------------
#         # CHIẾN THUẬT BURST CAPTURE (GHI LẠI MỌI BẰNG CHỨNG)
#         # -------------------------------------------------------------------
#         if not encodings:
#             log_app("debug", f"No face detected in frame (Attempt {attempt})")
#             # Vẫn lưu lại để làm bằng chứng (có thể kẻ gian đang lấy tay che camera)
#             await save_and_stage(processed, prefix=f"no_face_attempt_{attempt}")

#             best_result.attempts = attempt
#             await asyncio.sleep(FACE_CAPTURE_DELAY)
#             continue

#         name, distance = await loop.run_in_executor(
#             None, compare_faces, encodings[0], known, tolerance
#         )

#         # Cập nhật kết quả tốt nhất (khoảng cách gần nhất)
#         if distance < best_result.distance:
#             best_result.distance = distance
#             best_result.attempts = attempt

#         if name is not None:
#             # NHẬN DIỆN THÀNH CÔNG -> Lưu ảnh success và mở cửa ngay lập tức
#             staged = await save_and_stage(processed, prefix=f"success_{name}")
#             best_result.success = True
#             best_result.name = name
#             best_result.image_path = str(staged) if staged else None

#             log_event(
#                 EventType.FACE_SUCCESS,
#                 name=name,
#                 distance=round(distance, 4),
#                 attempt=attempt,
#                 image=best_result.image_path,
#             )
#             return best_result
#         else:
#             # NHẬN DIỆN THẤT BẠI (Có mặt người nhưng lạ) -> Lưu lại làm bằng chứng
#             staged = await save_and_stage(processed, prefix=f"unknown_attempt_{attempt}")
#             best_result.image_path = str(staged) if staged else None

#             await asyncio.sleep(FACE_CAPTURE_DELAY)

#     # =========================================================================
#     # KẾT THÚC VÒNG LẶP MÀ VẪN THẤT BẠI (Intruder Alert)
#     # =========================================================================
#     log_event(
#         EventType.FACE_FAILED,
#         attempts=max_attempts,
#         best_distance=round(best_result.distance, 4),
#         image=best_result.image_path, # Gửi kèm bức ảnh cuối cùng cùng với sự kiện lỗi
#     )

#     best_result.attempts = max_attempts
#     return best_result



# pi4/recognition/face_encoder.py
"""
THIẾT KẾ MỚI — Không phức tạp, không gây lỗi, đủ an toàn.

NGUYÊN TẮC:
  - Dùng face_recognition (dlib) NGUYÊN BẢN trên Pi — không hack, không monkey-patch.
  - Pi camera ra ảnh 640x480 RGB — kích thước này dlib HOG xử lý tốt, KHÔNG cần resize.
  - Chỉ 1 bước tiền xử lý: đảm bảo array là uint8 C-contiguous (fix lỗi dlib trên mọi nền tảng).
  - Tolerance 0.5 — vừa đủ an toàn (không nhận nhầm người lạ) vừa không quá khắt khe.
  - known_faces.pkl là nguồn sự thật duy nhất trên Pi.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

import numpy as np
import face_recognition as fr

from config.settings import settings
from logging_module.event_logger import log_app, log_event, EventType

FaceEncoding = np.ndarray
KnownFaces = dict[str, list[FaceEncoding]]

# Cache RAM — load 1 lần, dùng mãi
_known_faces: KnownFaces = {}
_encodings_loaded = False


# ── Bước tiền xử lý duy nhất ─────────────────────────────────────────────────

def _ensure_dlib_compatible(frame: np.ndarray) -> np.ndarray:
    """
    Đảm bảo array tương thích với dlib:
      - dtype = uint8
      - C-contiguous trong bộ nhớ (quan trọng nhất — dlib báo lỗi nếu không)
      - shape = (H, W, 3)

    Đây là nguyên nhân gốc rễ gây "Unsupported image type" trên Windows.
    Trên Pi thường không bị nhưng vẫn cần để an toàn.
    """
    img = frame
    # Xử lý RGBA hoặc grayscale
    if img.ndim == 2:
        img = np.stack([img, img, img], axis=2)
    elif img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]

    # QUAN TRỌNG: ascontiguousarray fix lỗi dlib "Unsupported image type"
    return np.ascontiguousarray(img, dtype=np.uint8)


# ── Load / Save known_faces.pkl ───────────────────────────────────────────────

def load_known_faces(force_reload: bool = False) -> KnownFaces:
    """Tải encodings từ pkl vào RAM. Cache lại để không đọc disk mỗi lần."""
    global _known_faces, _encodings_loaded

    if _encodings_loaded and not force_reload:
        return _known_faces

    path: Path = settings.encodings_path
    if not path.exists():
        log_app("warning", "known_faces.pkl not found — no faces enrolled yet", path=str(path))
        _known_faces = {}
        _encodings_loaded = True
        return _known_faces

    try:
        with open(path, "rb") as f:
            data = pickle.load(f)

        if not isinstance(data, dict):
            raise ValueError("pkl file must contain a dict")

        # Chỉ giữ entries hợp lệ (có ít nhất 1 encoding)
        _known_faces = {
            k: [np.ascontiguousarray(e, dtype=np.float64) for e in v]
            for k, v in data.items()
            if isinstance(v, list) and len(v) > 0
        }
        _encodings_loaded = True

        total = sum(len(v) for v in _known_faces.values())
        log_app("info", "Encodings loaded",
                people=list(_known_faces.keys()), total_samples=total)
        return _known_faces

    except Exception as exc:
        log_event(EventType.SYSTEM_ERROR, detail=f"load_known_faces: {exc}")
        _known_faces = {}
        _encodings_loaded = True
        return _known_faces


def save_known_faces(faces: KnownFaces) -> bool:
    """Lưu xuống pkl và cập nhật cache RAM."""
    global _known_faces, _encodings_loaded

    try:
        path = settings.encodings_path
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            pickle.dump(faces, f)

        _known_faces = faces
        _encodings_loaded = True

        log_app("info", "Encodings saved", people=list(faces.keys()))
        return True

    except Exception as exc:
        log_event(EventType.SYSTEM_ERROR, detail=f"save_known_faces: {exc}")
        return False


def reload_known_faces() -> KnownFaces:
    """Buộc reload từ disk — gọi sau khi Pi nhận tín hiệu sync từ Web."""
    return load_known_faces(force_reload=True)


# ── Detect và Encode ──────────────────────────────────────────────────────────

def encode_face(frame: np.ndarray) -> list[FaceEncoding]:
    """
    Nhận frame RGB 640x480 từ camera, trả về list encoding 128-d.
    Trả về [] nếu không tìm thấy mặt.

    Dùng HOG model — nhẹ, phù hợp Pi 4.
    upsample=1 để tăng khả năng detect mặt ở khoảng cách bình thường.
    """
    try:
        img = _ensure_dlib_compatible(frame)
        h, w = img.shape[:2]
        log_app("debug", f"encode_face: {w}x{h} frame")

        locations = fr.face_locations(img, model="hog", number_of_times_to_upsample=1)

        if not locations:
            log_app("debug", "encode_face: no face detected")
            return []

        log_app("debug", f"encode_face: {len(locations)} face(s) detected")

        encodings = fr.face_encodings(img, locations, num_jitters=1)
        return list(encodings)

    except Exception as exc:
        log_app("error", "encode_face failed", detail=str(exc))
        return []


# ── So sánh mặt ──────────────────────────────────────────────────────────────

def compare_faces(
    encoding: FaceEncoding,
    known: KnownFaces,
    tolerance: float | None = None,
) -> tuple[Optional[str], float]:
    """
    So sánh encoding với kho dữ liệu.
    Trả về (tên, khoảng cách) nếu match, (None, khoảng cách tốt nhất) nếu không.

    Tolerance mặc định 0.5:
      - < 0.45 : rất chắc chắn
      - 0.45–0.5: chấp nhận được
      - > 0.55 : có thể nhận nhầm — không nên dùng
    """
    if tolerance is None:
        tolerance = settings.face_tolerance

    if not known:
        return None, 1.0

    try:
        best_name: Optional[str] = None
        best_dist = 1.0

        for name, enc_list in known.items():
            dists = fr.face_distance(enc_list, encoding)
            if len(dists) == 0:
                continue
            min_dist = float(np.min(dists))
            log_app("debug", f"compare: {name} = {min_dist:.4f}")
            if min_dist < best_dist:
                best_dist = min_dist
                best_name = name

        if best_dist <= tolerance:
            log_app("info", f"MATCH: {best_name} @ {best_dist:.4f}")
            return best_name, best_dist

        log_app("info", f"NO MATCH. Best: {best_name} @ {best_dist:.4f}")
        return None, best_dist

    except Exception as exc:
        log_app("error", "compare_faces failed", detail=str(exc))
        return None, 1.0

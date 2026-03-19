# recognition/face_encoder.py
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Optional

import numpy as np

# Đưa import lên mức module để "Warm-up" (Tải sẵn) thư viện vào RAM khi khởi động.
# Tránh việc người dùng phải đứng đợi 3 giây ở lần mở cửa đầu tiên.
import face_recognition as fr

from config.settings import settings
from logging_module.event_logger import log_app, log_event, EventType

FaceEncoding = np.ndarray
KnownFaces   = dict[str, list[FaceEncoding]]

# Cache trên RAM để nhận diện tức thì, không phải đọc thẻ nhớ (SD Card) liên tục
_known_faces: KnownFaces = {}
_encodings_loaded = False


def load_known_faces(force_reload: bool = False) -> KnownFaces:
    """Tải dữ liệu khuôn mặt từ file .pkl vào RAM."""
    global _known_faces, _encodings_loaded

    if _encodings_loaded and not force_reload:
        return _known_faces

    path: Path = settings.encodings_path
    if not path.exists():
        log_app("warning", "Encodings file not found — starting empty", path=str(path))
        _known_faces = {}
        _encodings_loaded = True
        return _known_faces

    try:
        with open(path, "rb") as f:
            data = pickle.load(f)

        if not isinstance(data, dict):
            raise ValueError("Encodings file must contain a dict")

        # Lọc bỏ những records rác (không có encoding nào)
        _known_faces = {k: v for k, v in data.items() if isinstance(v, list) and len(v) > 0}
        _encodings_loaded = True

        log_app("info", "Encodings loaded",
                count=sum(len(v) for v in _known_faces.values()),
                people=list(_known_faces.keys()))

        return _known_faces

    except Exception as exc:
        log_event(EventType.SYSTEM_ERROR, detail=f"load_known_faces: {exc}")
        _known_faces = {}
        _encodings_loaded = True
        return _known_faces


def save_known_faces(faces: KnownFaces) -> bool:
    """Lưu dữ liệu khuôn mặt xuống thẻ nhớ và CẬP NHẬT CACHE."""
    global _known_faces, _encodings_loaded

    try:
        path = settings.encodings_path
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            pickle.dump(faces, f)

        # VÁ LỖI: Đồng bộ hóa Cache trên RAM ngay lập tức sau khi lưu
        _known_faces = faces
        _encodings_loaded = True

        log_app("info", "Encodings saved", people=list(faces.keys()))
        return True

    except Exception as exc:
        log_event(EventType.SYSTEM_ERROR, detail=f"save_known_faces: {exc}")
        return False


def encode_face(frame: np.ndarray) -> list[FaceEncoding]:
    """Tìm và trích xuất đặc trưng khuôn mặt từ khung hình."""
    try:
        # Dùng model 'hog' cực kỳ phù hợp và nhẹ cho chip ARM của Raspberry Pi
        locations = fr.face_locations(frame, model="hog")
        if not locations:
            return []

        encodings = fr.face_encodings(frame, locations)
        return encodings
    except Exception as exc:
        log_app("error", "encode_face error", detail=str(exc))
        return []


def compare_faces(
    encoding: FaceEncoding,
    known: KnownFaces,
    tolerance: float | None = None,
) -> tuple[Optional[str], float]:
    """
    So sánh khuôn mặt mới với kho dữ liệu (Nearest Neighbor).
    Trả về: (Tên người khớp nhất hoặc None, Khoảng cách sai số nhỏ nhất).
    """
    if tolerance is None:
        tolerance = settings.face_tolerance

    if not known:
        return None, 1.0

    try:
        best_name: Optional[str] = None
        best_dist = 1.0

        for name, enc_list in known.items():
            # face_distance trả về mảng khoảng cách của khuôn mặt mới so với TẤT CẢ các ảnh mẫu của 'name'
            dists = fr.face_distance(enc_list, encoding)
            if len(dists) == 0:
                continue

            # Lấy tấm ảnh giống nhất (khoảng cách nhỏ nhất) của người này
            min_dist = float(dists.min())

            # Cạnh tranh với những người khác để tìm ra ứng viên sáng giá nhất hệ thống
            if min_dist < best_dist:
                best_dist = min_dist
                best_name = name

        # Phán quyết cuối cùng của Vị Thẩm Phán
        if best_dist <= tolerance:
            return best_name, best_dist

        return None, best_dist

    except Exception as exc:
        log_app("error", "compare_faces error", detail=str(exc))
        return None, 1.0

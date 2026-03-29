# # # recognition/face_encoder.py
# # from __future__ import annotations

# # import pickle
# # from pathlib import Path
# # from typing import Optional

# # import numpy as np

# # # Đưa import lên mức module để "Warm-up" (Tải sẵn) thư viện vào RAM khi khởi động.
# # # Tránh việc người dùng phải đứng đợi 3 giây ở lần mở cửa đầu tiên.
# # import face_recognition as fr

# # from config.settings import settings
# # from logging_module.event_logger import log_app, log_event, EventType

# # FaceEncoding = np.ndarray
# # KnownFaces   = dict[str, list[FaceEncoding]]

# # # Cache trên RAM để nhận diện tức thì, không phải đọc thẻ nhớ (SD Card) liên tục
# # _known_faces: KnownFaces = {}
# # _encodings_loaded = False


# # def load_known_faces(force_reload: bool = False) -> KnownFaces:
# #     """Tải dữ liệu khuôn mặt từ file .pkl vào RAM."""
# #     global _known_faces, _encodings_loaded

# #     if _encodings_loaded and not force_reload:
# #         return _known_faces

# #     path: Path = settings.encodings_path
# #     if not path.exists():
# #         log_app("warning", "Encodings file not found — starting empty", path=str(path))
# #         _known_faces = {}
# #         _encodings_loaded = True
# #         return _known_faces

# #     try:
# #         with open(path, "rb") as f:
# #             data = pickle.load(f)

# #         if not isinstance(data, dict):
# #             raise ValueError("Encodings file must contain a dict")

# #         # Lọc bỏ những records rác (không có encoding nào)
# #         _known_faces = {k: v for k, v in data.items() if isinstance(v, list) and len(v) > 0}
# #         _encodings_loaded = True

# #         log_app("info", "Encodings loaded",
# #                 count=sum(len(v) for v in _known_faces.values()),
# #                 people=list(_known_faces.keys()))

# #         return _known_faces

# #     except Exception as exc:
# #         log_event(EventType.SYSTEM_ERROR, detail=f"load_known_faces: {exc}")
# #         _known_faces = {}
# #         _encodings_loaded = True
# #         return _known_faces


# # def save_known_faces(faces: KnownFaces) -> bool:
# #     """Lưu dữ liệu khuôn mặt xuống thẻ nhớ và CẬP NHẬT CACHE."""
# #     global _known_faces, _encodings_loaded

# #     try:
# #         path = settings.encodings_path
# #         path.parent.mkdir(parents=True, exist_ok=True)

# #         with open(path, "wb") as f:
# #             pickle.dump(faces, f)

# #         # VÁ LỖI: Đồng bộ hóa Cache trên RAM ngay lập tức sau khi lưu
# #         _known_faces = faces
# #         _encodings_loaded = True

# #         log_app("info", "Encodings saved", people=list(faces.keys()))
# #         return True

# #     except Exception as exc:
# #         log_event(EventType.SYSTEM_ERROR, detail=f"save_known_faces: {exc}")
# #         return False


# # def encode_face(frame: np.ndarray) -> list[FaceEncoding]:
# #     """Tìm và trích xuất đặc trưng khuôn mặt từ khung hình."""
# #     try:
# #         # Dùng model 'hog' cực kỳ phù hợp và nhẹ cho chip ARM của Raspberry Pi
# #         locations = fr.face_locations(frame, model="hog")
# #         if not locations:
# #             return []

# #         encodings = fr.face_encodings(frame, locations)
# #         return encodings
# #     except Exception as exc:
# #         log_app("error", "encode_face error", detail=str(exc))
# #         return []


# # def compare_faces(
# #     encoding: FaceEncoding,
# #     known: KnownFaces,
# #     tolerance: float | None = None,
# # ) -> tuple[Optional[str], float]:
# #     """
# #     So sánh khuôn mặt mới với kho dữ liệu (Nearest Neighbor).
# #     Trả về: (Tên người khớp nhất hoặc None, Khoảng cách sai số nhỏ nhất).
# #     """
# #     if tolerance is None:
# #         tolerance = settings.face_tolerance

# #     if not known:
# #         return None, 1.0

# #     try:
# #         best_name: Optional[str] = None
# #         best_dist = 1.0

# #         for name, enc_list in known.items():
# #             # face_distance trả về mảng khoảng cách của khuôn mặt mới so với TẤT CẢ các ảnh mẫu của 'name'
# #             dists = fr.face_distance(enc_list, encoding)
# #             if len(dists) == 0:
# #                 continue

# #             # Lấy tấm ảnh giống nhất (khoảng cách nhỏ nhất) của người này
# #             min_dist = float(dists.min())

# #             # Cạnh tranh với những người khác để tìm ra ứng viên sáng giá nhất hệ thống
# #             if min_dist < best_dist:
# #                 best_dist = min_dist
# #                 best_name = name

# #         # Phán quyết cuối cùng của Vị Thẩm Phán
# #         if best_dist <= tolerance:
# #             return best_name, best_dist

# #         return None, best_dist

# #     except Exception as exc:
# #         log_app("error", "compare_faces error", detail=str(exc))
# #         return None, 1.0



# # # pi4/recognition/face_encoder.py
# # """
# # THIẾT KẾ MỚI — Không phức tạp, không gây lỗi, đủ an toàn.

# # NGUYÊN TẮC:
# #   - Dùng face_recognition (dlib) NGUYÊN BẢN trên Pi — không hack, không monkey-patch.
# #   - Pi camera ra ảnh 640x480 RGB — kích thước này dlib HOG xử lý tốt, KHÔNG cần resize.
# #   - Chỉ 1 bước tiền xử lý: đảm bảo array là uint8 C-contiguous (fix lỗi dlib trên mọi nền tảng).
# #   - Tolerance 0.5 — vừa đủ an toàn (không nhận nhầm người lạ) vừa không quá khắt khe.
# #   - known_faces.pkl là nguồn sự thật duy nhất trên Pi.
# # """
# # from __future__ import annotations

# # import pickle
# # from pathlib import Path
# # from typing import Optional

# # import numpy as np
# # import face_recognition as fr

# # from config.settings import settings
# # from logging_module.event_logger import log_app, log_event, EventType

# # FaceEncoding = np.ndarray
# # KnownFaces = dict[str, list[FaceEncoding]]

# # # Cache RAM — load 1 lần, dùng mãi
# # _known_faces: KnownFaces = {}
# # _encodings_loaded = False


# # # ── Bước tiền xử lý duy nhất ─────────────────────────────────────────────────

# # def _ensure_dlib_compatible(frame: np.ndarray) -> np.ndarray:
# #     """
# #     Đảm bảo array tương thích với dlib:
# #       - dtype = uint8
# #       - C-contiguous trong bộ nhớ (quan trọng nhất — dlib báo lỗi nếu không)
# #       - shape = (H, W, 3)

# #     Đây là nguyên nhân gốc rễ gây "Unsupported image type" trên Windows.
# #     Trên Pi thường không bị nhưng vẫn cần để an toàn.
# #     """
# #     img = frame
# #     # Xử lý RGBA hoặc grayscale
# #     if img.ndim == 2:
# #         img = np.stack([img, img, img], axis=2)
# #     elif img.ndim == 3 and img.shape[2] == 4:
# #         img = img[:, :, :3]

# #     # QUAN TRỌNG: ascontiguousarray fix lỗi dlib "Unsupported image type"
# #     return np.ascontiguousarray(img, dtype=np.uint8)


# # # ── Load / Save known_faces.pkl ───────────────────────────────────────────────

# # def load_known_faces(force_reload: bool = False) -> KnownFaces:
# #     """Tải encodings từ pkl vào RAM. Cache lại để không đọc disk mỗi lần."""
# #     global _known_faces, _encodings_loaded

# #     if _encodings_loaded and not force_reload:
# #         return _known_faces

# #     path: Path = settings.encodings_path
# #     if not path.exists():
# #         log_app("warning", "known_faces.pkl not found — no faces enrolled yet", path=str(path))
# #         _known_faces = {}
# #         _encodings_loaded = True
# #         return _known_faces

# #     try:
# #         with open(path, "rb") as f:
# #             data = pickle.load(f)

# #         if not isinstance(data, dict):
# #             raise ValueError("pkl file must contain a dict")

# #         # Chỉ giữ entries hợp lệ (có ít nhất 1 encoding)
# #         _known_faces = {
# #             k: [np.ascontiguousarray(e, dtype=np.float64) for e in v]
# #             for k, v in data.items()
# #             if isinstance(v, list) and len(v) > 0
# #         }
# #         _encodings_loaded = True

# #         total = sum(len(v) for v in _known_faces.values())
# #         log_app("info", "Encodings loaded",
# #                 people=list(_known_faces.keys()), total_samples=total)
# #         return _known_faces

# #     except Exception as exc:
# #         log_event(EventType.SYSTEM_ERROR, detail=f"load_known_faces: {exc}")
# #         _known_faces = {}
# #         _encodings_loaded = True
# #         return _known_faces


# # def save_known_faces(faces: KnownFaces) -> bool:
# #     """Lưu xuống pkl và cập nhật cache RAM."""
# #     global _known_faces, _encodings_loaded

# #     try:
# #         path = settings.encodings_path
# #         path.parent.mkdir(parents=True, exist_ok=True)

# #         with open(path, "wb") as f:
# #             pickle.dump(faces, f)

# #         _known_faces = faces
# #         _encodings_loaded = True

# #         log_app("info", "Encodings saved", people=list(faces.keys()))
# #         return True

# #     except Exception as exc:
# #         log_event(EventType.SYSTEM_ERROR, detail=f"save_known_faces: {exc}")
# #         return False


# # def reload_known_faces() -> KnownFaces:
# #     """Buộc reload từ disk — gọi sau khi Pi nhận tín hiệu sync từ Web."""
# #     return load_known_faces(force_reload=True)


# # # ── Detect và Encode ──────────────────────────────────────────────────────────

# # def encode_face(frame: np.ndarray) -> list[FaceEncoding]:
# #     """
# #     Nhận frame RGB 640x480 từ camera, trả về list encoding 128-d.
# #     Trả về [] nếu không tìm thấy mặt.

# #     Dùng HOG model — nhẹ, phù hợp Pi 4.
# #     upsample=1 để tăng khả năng detect mặt ở khoảng cách bình thường.
# #     """
# #     try:
# #         img = _ensure_dlib_compatible(frame)
# #         h, w = img.shape[:2]
# #         log_app("debug", f"encode_face: {w}x{h} frame")

# #         locations = fr.face_locations(img, model="hog", number_of_times_to_upsample=1)

# #         if not locations:
# #             log_app("debug", "encode_face: no face detected")
# #             return []

# #         log_app("debug", f"encode_face: {len(locations)} face(s) detected")

# #         encodings = fr.face_encodings(img, locations, num_jitters=1)
# #         return list(encodings)

# #     except Exception as exc:
# #         log_app("error", "encode_face failed", detail=str(exc))
# #         return []


# # # ── So sánh mặt ──────────────────────────────────────────────────────────────

# # def compare_faces(
# #     encoding: FaceEncoding,
# #     known: KnownFaces,
# #     tolerance: float | None = None,
# # ) -> tuple[Optional[str], float]:
# #     """
# #     So sánh encoding với kho dữ liệu.
# #     Trả về (tên, khoảng cách) nếu match, (None, khoảng cách tốt nhất) nếu không.

# #     Tolerance mặc định 0.5:
# #       - < 0.45 : rất chắc chắn
# #       - 0.45–0.5: chấp nhận được
# #       - > 0.55 : có thể nhận nhầm — không nên dùng
# #     """
# #     if tolerance is None:
# #         tolerance = settings.face_tolerance

# #     if not known:
# #         return None, 1.0

# #     try:
# #         best_name: Optional[str] = None
# #         best_dist = 1.0

# #         for name, enc_list in known.items():
# #             dists = fr.face_distance(enc_list, encoding)
# #             if len(dists) == 0:
# #                 continue
# #             min_dist = float(np.min(dists))
# #             log_app("debug", f"compare: {name} = {min_dist:.4f}")
# #             if min_dist < best_dist:
# #                 best_dist = min_dist
# #                 best_name = name

# #         if best_dist <= tolerance:
# #             log_app("info", f"MATCH: {best_name} @ {best_dist:.4f}")
# #             return best_name, best_dist

# #         log_app("info", f"NO MATCH. Best: {best_name} @ {best_dist:.4f}")
# #         return None, best_dist

# #     except Exception as exc:
# #         log_app("error", "compare_faces failed", detail=str(exc))
# #         return None, 1.0

# # pi4/recognition/face_encoder.py
# """
# THIẾT KẾ MỚI — Không phức tạp, không gây lỗi, đủ an toàn.

# NGUYÊN TẮC:
#   - Dùng face_recognition (dlib) NGUYÊN BẢN trên Pi — không hack, không monkey-patch.
#   - Pi camera ra ảnh 640x480 RGB — kích thước này dlib HOG xử lý tốt, KHÔNG cần resize.
#   - Chỉ 1 bước tiền xử lý: đảm bảo array là uint8 C-contiguous (fix lỗi dlib trên mọi nền tảng).
#   - Tolerance 0.5 — vừa đủ an toàn (không nhận nhầm người lạ) vừa không quá khắt khe.
#   - known_faces.pkl là nguồn sự thật duy nhất trên Pi.
# """
# from __future__ import annotations

# import pickle
# from pathlib import Path
# from typing import Optional

# import numpy as np
# import face_recognition as fr

# from config.settings import settings
# from logging_module.event_logger import log_app, log_event, EventType

# FaceEncoding = np.ndarray
# KnownFaces = dict[str, list[FaceEncoding]]

# # Cache RAM — load 1 lần, dùng mãi
# _known_faces: KnownFaces = {}
# _encodings_loaded = False


# # ── Bước tiền xử lý duy nhất ─────────────────────────────────────────────────

# def _ensure_dlib_compatible(frame: np.ndarray) -> np.ndarray:
#     """
#     Đảm bảo array tương thích với dlib:
#       - dtype = uint8
#       - C-contiguous trong bộ nhớ (quan trọng nhất — dlib báo lỗi nếu không)
#       - shape = (H, W, 3)

#     Đây là nguyên nhân gốc rễ gây "Unsupported image type" trên Windows.
#     Trên Pi thường không bị nhưng vẫn cần để an toàn.
#     """
#     img = frame
#     # Xử lý RGBA hoặc grayscale
#     if img.ndim == 2:
#         img = np.stack([img, img, img], axis=2)
#     elif img.ndim == 3 and img.shape[2] == 4:
#         img = img[:, :, :3]

#     # QUAN TRỌNG: ascontiguousarray fix lỗi dlib "Unsupported image type"
#     return np.ascontiguousarray(img, dtype=np.uint8)


# # ── Load / Save known_faces.pkl ───────────────────────────────────────────────

# def load_known_faces(force_reload: bool = False) -> KnownFaces:
#     """Tải encodings từ pkl vào RAM. Cache lại để không đọc disk mỗi lần."""
#     global _known_faces, _encodings_loaded

#     if _encodings_loaded and not force_reload:
#         return _known_faces

#     path: Path = settings.encodings_path
#     if not path.exists():
#         log_app("warning", "known_faces.pkl not found — no faces enrolled yet", path=str(path))
#         _known_faces = {}
#         _encodings_loaded = True
#         return _known_faces

#     try:
#         with open(path, "rb") as f:
#             data = pickle.load(f)

#         if not isinstance(data, dict):
#             raise ValueError("pkl file must contain a dict")

#         # Chỉ giữ entries hợp lệ (có ít nhất 1 encoding)
#         _known_faces = {
#             k: [np.ascontiguousarray(e, dtype=np.float64) for e in v]
#             for k, v in data.items()
#             if isinstance(v, list) and len(v) > 0
#         }
#         _encodings_loaded = True

#         total = sum(len(v) for v in _known_faces.values())
#         log_app("info", "Encodings loaded",
#                 people=list(_known_faces.keys()), total_samples=total)
#         return _known_faces

#     except Exception as exc:
#         log_event(EventType.SYSTEM_ERROR, detail=f"load_known_faces: {exc}")
#         _known_faces = {}
#         _encodings_loaded = True
#         return _known_faces


# def save_known_faces(faces: KnownFaces) -> bool:
#     """Lưu xuống pkl và cập nhật cache RAM."""
#     global _known_faces, _encodings_loaded

#     try:
#         path = settings.encodings_path
#         path.parent.mkdir(parents=True, exist_ok=True)

#         with open(path, "wb") as f:
#             pickle.dump(faces, f)

#         _known_faces = faces
#         _encodings_loaded = True

#         log_app("info", "Encodings saved", people=list(faces.keys()))
#         return True

#     except Exception as exc:
#         log_event(EventType.SYSTEM_ERROR, detail=f"save_known_faces: {exc}")
#         return False


# def reload_known_faces() -> KnownFaces:
#     """Buộc reload từ disk — gọi sau khi Pi nhận tín hiệu sync từ Web."""
#     return load_known_faces(force_reload=True)


# # ── Detect và Encode ──────────────────────────────────────────────────────────

# def encode_face(frame: np.ndarray) -> list[FaceEncoding]:
#     """
#     Nhận frame RGB 640x480 từ camera, trả về list encoding 128-d.
#     Trả về [] nếu không tìm thấy mặt.

#     Dùng HOG model — nhẹ, phù hợp Pi 4.
#     upsample=1 để tăng khả năng detect mặt ở khoảng cách bình thường.
#     """
#     try:
#         img = _ensure_dlib_compatible(frame)
#         h, w = img.shape[:2]
#         log_app("debug", f"encode_face: {w}x{h} frame")

#         locations = fr.face_locations(img, model="hog", number_of_times_to_upsample=1)

#         if not locations:
#             log_app("debug", "encode_face: no face detected")
#             return []

#         log_app("debug", f"encode_face: {len(locations)} face(s) detected")

#         encodings = fr.face_encodings(img, locations, num_jitters=1)
#         return list(encodings)

#     except Exception as exc:
#         log_app("error", "encode_face failed", detail=str(exc))
#         return []


# # ── So sánh mặt ──────────────────────────────────────────────────────────────

# def compare_faces(
#     encoding: FaceEncoding,
#     known: KnownFaces,
#     tolerance: float | None = None,
# ) -> tuple[Optional[str], float]:
#     """
#     So sánh encoding với kho dữ liệu.
#     Trả về (tên, khoảng cách) nếu match, (None, khoảng cách tốt nhất) nếu không.

#     Tolerance mặc định 0.5:
#       - < 0.45 : rất chắc chắn
#       - 0.45–0.5: chấp nhận được
#       - > 0.55 : có thể nhận nhầm — không nên dùng
#     """
#     if tolerance is None:
#         tolerance = settings.face_tolerance

#     if not known:
#         return None, 1.0

#     try:
#         best_name: Optional[str] = None
#         best_dist = 1.0

#         for name, enc_list in known.items():
#             dists = fr.face_distance(enc_list, encoding)
#             if len(dists) == 0:
#                 continue
#             min_dist = float(np.min(dists))
#             log_app("debug", f"compare: {name} = {min_dist:.4f}")
#             if min_dist < best_dist:
#                 best_dist = min_dist
#                 best_name = name

#         if best_dist <= tolerance:
#             log_app("info", f"MATCH: {best_name} @ {best_dist:.4f}")
#             return best_name, best_dist

#         log_app("info", f"NO MATCH. Best: {best_name} @ {best_dist:.4f}")
#         return None, best_dist

#     except Exception as exc:
#         log_app("error", "compare_faces failed", detail=str(exc))
#         return None, 1.0



# pi4/recognition/face_encoder.py
"""
THIẾT KẾ MỚI — Nâng cấp AI "Dynamic Tolerance" (Sai số động).

NGUYÊN TẮC:
  - Vẫn dùng dlib HOG nguyên bản (nhẹ, ổn định cho Pi 4).
  - Đảm bảo array là uint8 C-contiguous để chống lỗi memory.
  - CẢI TIẾN: Áp dụng Ratio Test (So sánh chéo). Nếu ảnh bị nhiễu/thiếu sáng
    khiến distance tăng > 0.5, hệ thống sẽ kiểm tra mức độ "độc tôn".
    Nếu nó vẫn khác biệt rõ ràng với người giống thứ 2, vẫn cho phép mở cửa!
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
    """
    try:
        img = _ensure_dlib_compatible(frame)
        h, w = img.shape[:2]

        locations = fr.face_locations(img, model="hog", number_of_times_to_upsample=1)

        if not locations:
            return []

        encodings = fr.face_encodings(img, locations, num_jitters=1)
        return list(encodings)

    except Exception as exc:
        log_app("error", "encode_face failed", detail=str(exc))
        return []


# ── So sánh mặt (DYNAMIC TOLERANCE) ───────────────────────────────────────────

def compare_faces(
    encoding: FaceEncoding,
    known: KnownFaces,
    tolerance: float | None = None,
) -> tuple[Optional[str], float]:
    """
    So sánh encoding với kho dữ liệu kết hợp cơ chế SAI SỐ ĐỘNG.
    Tránh việc từ chối sai khi môi trường thực tế bị thiếu sáng/ngược sáng.
    """
    if tolerance is None:
        tolerance = settings.face_tolerance

    if not known:
        return None, 1.0

    try:
        candidates = []

        # 1. Tính toán khoảng cách (độ lệch) tới tất cả mọi người trong DB
        for name, enc_list in known.items():
            dists = fr.face_distance(enc_list, encoding)
            if len(dists) == 0:
                continue
            min_dist = float(np.min(dists))
            candidates.append((name, min_dist))

        if not candidates:
            return None, 1.0

        # 2. Sắp xếp để tìm ra người giống nhất và giống nhì
        candidates.sort(key=lambda x: x[1])
        best_name, best_dist = candidates[0]

        # -- KIỂM TRA MỨC 1: LÝ TƯỞNG --
        if best_dist <= tolerance:
            log_app("info", f"MATCH (Strict): {best_name} @ {best_dist:.4f}")
            return best_name, best_dist

        # -- KIỂM TRA MỨC 2: SAI SỐ ĐỘNG (Bù trừ nhiễu vật lý) --
        # Cho phép nới lỏng thêm 0.08 nếu ảnh bị mờ/tối
        margin_tolerance = tolerance + 0.08

        if best_dist <= margin_tolerance:
            # Nếu DB chỉ có 1 người, ta nới lỏng luôn vì không sợ nhầm với ai
            if len(candidates) == 1:
                log_app("info", f"MATCH (Dynamic-Single): {best_name} @ {best_dist:.4f}")
                return best_name, best_dist

            # Nếu DB có nhiều người, dùng Ratio Test (Tỷ lệ phân biệt)
            else:
                second_best_dist = candidates[1][1]
                ratio = best_dist / second_best_dist

                # Nếu khoảng cách của người số 1 vượt trội hơn người số 2 ít nhất 15%
                # Chứng tỏ hệ thống chắc chắn đây là người số 1 (chỉ là ảnh hơi xấu)
                if ratio < 0.85:
                    log_app("info", f"MATCH (Dynamic-Ratio {ratio:.2f}): {best_name} @ {best_dist:.4f}")
                    return best_name, best_dist

        # Từ chối nếu vượt mọi bài test
        log_app("info", f"NO MATCH. Best: {best_name} @ {best_dist:.4f}")
        return None, best_dist

    except Exception as exc:
        log_app("error", "compare_faces failed", detail=str(exc))
        return None, 1.0

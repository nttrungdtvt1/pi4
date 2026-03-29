# # # vision/frame_processor.py
# # """
# # Tiền xử lý ảnh trước khi đưa vào face_recognition.
# # Input: numpy array RGB từ camera_manager
# # Output: numpy array RGB đã resize/normalize
# # """
# # from __future__ import annotations
# # from typing import Optional
# # import numpy as np
# # from config.constants import CAMERA_WIDTH, CAMERA_HEIGHT
# # from logging_module.event_logger import log_app


# # def resize_frame(frame: np.ndarray,
# #                  width: int = CAMERA_WIDTH,
# #                  height: int = CAMERA_HEIGHT) -> np.ndarray:
# #     """Resize về kích thước chuẩn (nhanh hơn khi nhận diện)."""
# #     import cv2
# #     h, w = frame.shape[:2]
# #     if (w, h) == (width, height):
# #         return frame
# #     return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


# # def ensure_rgb(frame: np.ndarray) -> np.ndarray:
# #     """Đảm bảo frame là RGB (3 channel). Từ chối RGBA, grayscale."""
# #     if frame.ndim == 2:
# #         import cv2
# #         return cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
# #     if frame.shape[2] == 4:
# #         return frame[:, :, :3]
# #     return frame


# # def preprocess(frame: Optional[np.ndarray]) -> Optional[np.ndarray]:
# #     """
# #     Pipeline hoàn chỉnh: validate → ensure_rgb → resize.
# #     Trả về None nếu frame không hợp lệ.
# #     """
# #     if frame is None:
# #         return None
# #     if not isinstance(frame, np.ndarray) or frame.size == 0:
# #         log_app("warning", "preprocess: invalid frame received")
# #         return None
# #     try:
# #         frame = ensure_rgb(frame)
# #         frame = resize_frame(frame)
# #         return frame
# #     except Exception as exc:
# #         log_app("error", "preprocess error", detail=str(exc))
# #         return None



# # vision/frame_processor.py
# """
# Tiền xử lý ảnh trước khi đưa vào face_recognition.
# Input: numpy array RGB từ camera_manager
# Output: numpy array RGB đã resize/normalize
# """
# from __future__ import annotations
# from typing import Optional
# import numpy as np
# from config.constants import CAMERA_WIDTH, CAMERA_HEIGHT
# from logging_module.event_logger import log_app


# def resize_frame(frame: np.ndarray,
#                  width: int = CAMERA_WIDTH,
#                  height: int = CAMERA_HEIGHT) -> np.ndarray:
#     """Resize về kích thước chuẩn (nhanh hơn khi nhận diện)."""
#     import cv2
#     h, w = frame.shape[:2]
#     if (w, h) == (width, height):
#         return frame
#     return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


# def ensure_rgb(frame: np.ndarray) -> np.ndarray:
#     """Đảm bảo frame là RGB (3 channel). Từ chối RGBA, grayscale."""
#     if frame.ndim == 2:
#         import cv2
#         return cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
#     if frame.shape[2] == 4:
#         return frame[:, :, :3]
#     return frame


# def preprocess(frame: Optional[np.ndarray]) -> Optional[np.ndarray]:
#     """
#     Pipeline hoàn chỉnh: validate → ensure_rgb → resize.
#     Trả về None nếu frame không hợp lệ.
#     """
#     if frame is None:
#         return None
#     if not isinstance(frame, np.ndarray) or frame.size == 0:
#         log_app("warning", "preprocess: invalid frame received")
#         return None
#     try:
#         frame = ensure_rgb(frame)
#         frame = resize_frame(frame)
#         return frame
#     except Exception as exc:
#         log_app("error", "preprocess error", detail=str(exc))
#         return None


# pi4/vision/frame_processor.py
"""
Tiền xử lý ảnh trước khi đưa vào face_recognition.
Input: numpy array RGB từ camera_manager
Output: numpy array RGB đã resize/normalize và CHỐNG NGƯỢC SÁNG
"""
from __future__ import annotations
from typing import Optional
import numpy as np
import cv2

from config.constants import CAMERA_WIDTH, CAMERA_HEIGHT
from logging_module.event_logger import log_app


def resize_frame(frame: np.ndarray,
                 width: int = CAMERA_WIDTH,
                 height: int = CAMERA_HEIGHT) -> np.ndarray:
    """Resize về kích thước chuẩn (nhanh hơn khi nhận diện)."""
    h, w = frame.shape[:2]
    if (w, h) == (width, height):
        return frame
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def ensure_rgb(frame: np.ndarray) -> np.ndarray:
    """Đảm bảo frame là RGB (3 channel). Từ chối RGBA, grayscale."""
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    if frame.shape[2] == 4:
        return frame[:, :, :3]
    return frame


def apply_clahe_rgb(frame: np.ndarray) -> np.ndarray:
    """
    NÂNG CẤP AI: Tự động cân bằng sáng cục bộ (CLAHE) để chống ngược sáng cực mạnh.
    Chỉ can thiệp vào kênh độ sáng (Lightness - L) nên không làm sai lệch màu da người.
    Giúp AI vẫn đọc được mặt khi bị ngược bóng đèn hoặc ánh sáng mặt trời.
    """
    try:
        # Chuyển đổi RGB sang không gian màu LAB để tách riêng lớp ánh sáng
        lab = cv2.cvtColor(frame, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)

        # Cân bằng ánh sáng cục bộ (ClipLimit 2.0, Grid 8x8 là tối ưu nhất cho khuôn mặt)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)

        # Gộp lại và chuyển về RGB
        limg = cv2.merge((cl, a, b))
        final_rgb = cv2.cvtColor(limg, cv2.COLOR_LAB2RGB)

        return final_rgb
    except Exception as exc:
        log_app("warning", "apply_clahe_rgb error, using original frame", detail=str(exc))
        return frame  # Fallback an toàn, nếu lỗi thì vẫn trả về ảnh gốc


def preprocess(frame: Optional[np.ndarray]) -> Optional[np.ndarray]:
    """
    Pipeline hoàn chỉnh: validate → ensure_rgb → resize → CLAHE (Chống ngược sáng).
    Trả về None nếu frame không hợp lệ.
    """
    if frame is None:
        return None
    if not isinstance(frame, np.ndarray) or frame.size == 0:
        log_app("warning", "preprocess: invalid frame received")
        return None

    try:
        # 1. Chuẩn hóa định dạng màu
        frame = ensure_rgb(frame)

        # 2. Resize để AI chạy mượt hơn trên Pi 4
        frame = resize_frame(frame)

        # 3. Kéo sáng / Chống ngược sáng để AI nhìn rõ mặt
        frame = apply_clahe_rgb(frame)

        return frame

    except Exception as exc:
        log_app("error", "preprocess error", detail=str(exc))
        return None

# vision/frame_processor.py
"""
Tiền xử lý ảnh trước khi đưa vào face_recognition.
Input: numpy array RGB từ camera_manager
Output: numpy array RGB đã resize/normalize
"""
from __future__ import annotations
from typing import Optional
import numpy as np
from config.constants import CAMERA_WIDTH, CAMERA_HEIGHT
from logging_module.event_logger import log_app


def resize_frame(frame: np.ndarray,
                 width: int = CAMERA_WIDTH,
                 height: int = CAMERA_HEIGHT) -> np.ndarray:
    """Resize về kích thước chuẩn (nhanh hơn khi nhận diện)."""
    import cv2
    h, w = frame.shape[:2]
    if (w, h) == (width, height):
        return frame
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def ensure_rgb(frame: np.ndarray) -> np.ndarray:
    """Đảm bảo frame là RGB (3 channel). Từ chối RGBA, grayscale."""
    if frame.ndim == 2:
        import cv2
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    if frame.shape[2] == 4:
        return frame[:, :, :3]
    return frame


def preprocess(frame: Optional[np.ndarray]) -> Optional[np.ndarray]:
    """
    Pipeline hoàn chỉnh: validate → ensure_rgb → resize.
    Trả về None nếu frame không hợp lệ.
    """
    if frame is None:
        return None
    if not isinstance(frame, np.ndarray) or frame.size == 0:
        log_app("warning", "preprocess: invalid frame received")
        return None
    try:
        frame = ensure_rgb(frame)
        frame = resize_frame(frame)
        return frame
    except Exception as exc:
        log_app("error", "preprocess error", detail=str(exc))
        return None

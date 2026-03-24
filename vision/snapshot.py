# # vision/snapshot.py
# """
# Lưu ảnh snapshot khi có sự kiện an ninh.
# Tách riêng khỏi cloud_uploader: lưu local vào thư mục tạm trước, upload chạy ngầm sau.
# """
# from __future__ import annotations

# import asyncio
# from datetime import datetime
# from pathlib import Path
# from typing import Optional

# import numpy as np

# # Mang cv2 lên đầu file để tránh latency (độ trễ) lúc đang xử lý sự kiện khẩn cấp
# import cv2

# from config.settings import settings
# from config.constants import UPLOAD_QUALITY
# from logging_module.event_logger import log_app, log_event, EventType


# def _timestamp_filename(prefix: str = "capture") -> str:
#     """Tạo tên file theo timestamp chuẩn đến mili-giây để chống ghi đè."""
#     ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Lấy 3 số thập phân của ms
#     return f"{prefix}_{ts}.jpg"


# def save_local(
#     frame: np.ndarray,
#     prefix: str = "capture",
#     directory: Optional[Path] = None
# ) -> Optional[Path]:
#     """
#     Lưu frame vào thẻ nhớ (Chạy đồng bộ/Blocking, nên được gọi qua ThreadPool).
#     Trả về Path tuyệt đối của file đã lưu, hoặc None nếu có lỗi.
#     """
#     try:
#         target_dir = directory or settings.captures_dir
#         target_dir.mkdir(parents=True, exist_ok=True)

#         filename = _timestamp_filename(prefix)
#         path = target_dir / filename

#         # Lật ngược hệ màu RGB → BGR vì OpenCV luôn lưu file ảnh dưới dạng BGR
#         bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

#         # Lưu ảnh và nén JPEG để tiết kiệm thẻ nhớ & băng thông mạng
#         ok  = cv2.imwrite(
#             str(path),
#             bgr,
#             [cv2.IMWRITE_JPEG_QUALITY, UPLOAD_QUALITY]
#         )

#         if not ok:
#             raise RuntimeError("cv2.imwrite returned False. Is SD card full or write-protected?")

#         log_app("debug", "Snapshot saved locally", path=str(path))
#         return path

#     except Exception as exc:
#         log_event(EventType.SYSTEM_ERROR, detail=f"save_local failed: {exc}")
#         return None


# async def save_and_stage(
#     frame: np.ndarray,
#     prefix: str = "capture"
# ) -> Optional[Path]:
#     """
#     Async wrapper: Lưu ảnh trực tiếp vào thư mục temp_uploads/
#     để cloud_uploader tự động "hốt" lên Cloud sau khi nhận diện xong.
#     Không làm block Event Loop chính.
#     """
#     loop = asyncio.get_running_loop()

#     # Ném tác vụ ghi thẻ nhớ chậm chạp xuống ThreadPool
#     path = await loop.run_in_executor(
#         None, save_local, frame, prefix, settings.temp_upload_dir
#     )
#     return path



# vision/snapshot.py
"""
Lưu ảnh snapshot khi có sự kiện an ninh.
Tách riêng khỏi cloud_uploader: lưu local vào thư mục tạm trước, upload chạy ngầm sau.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

# Mang cv2 lên đầu file để tránh latency (độ trễ) lúc đang xử lý sự kiện khẩn cấp
import cv2

from config.settings import settings
from config.constants import UPLOAD_QUALITY
from logging_module.event_logger import log_app, log_event, EventType


def _timestamp_filename(prefix: str = "capture") -> str:
    """Tạo tên file theo timestamp chuẩn đến mili-giây để chống ghi đè."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Lấy 3 số thập phân của ms
    return f"{prefix}_{ts}.jpg"


def save_local(
    frame: np.ndarray,
    prefix: str = "capture",
    directory: Optional[Path] = None
) -> Optional[Path]:
    """
    Lưu frame vào thẻ nhớ (Chạy đồng bộ/Blocking, nên được gọi qua ThreadPool).
    Trả về Path tuyệt đối của file đã lưu, hoặc None nếu có lỗi.
    """
    try:
        target_dir = directory or settings.captures_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = _timestamp_filename(prefix)
        path = target_dir / filename

        # Lật ngược hệ màu RGB → BGR vì OpenCV luôn lưu file ảnh dưới dạng BGR
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # Lưu ảnh và nén JPEG để tiết kiệm thẻ nhớ & băng thông mạng
        ok  = cv2.imwrite(
            str(path),
            bgr,
            [cv2.IMWRITE_JPEG_QUALITY, UPLOAD_QUALITY]
        )

        if not ok:
            raise RuntimeError("cv2.imwrite returned False. Is SD card full or write-protected?")

        log_app("debug", "Snapshot saved locally", path=str(path))
        return path

    except Exception as exc:
        log_event(EventType.SYSTEM_ERROR, detail=f"save_local failed: {exc}")
        return None


async def save_and_stage(
    frame: np.ndarray,
    prefix: str = "capture"
) -> Optional[Path]:
    """
    Async wrapper: Lưu ảnh trực tiếp vào thư mục temp_uploads/
    để cloud_uploader tự động "hốt" lên Cloud sau khi nhận diện xong.
    Không làm block Event Loop chính.
    """
    loop = asyncio.get_running_loop()

    # Ném tác vụ ghi thẻ nhớ chậm chạp xuống ThreadPool
    path = await loop.run_in_executor(
        None, save_local, frame, prefix, settings.temp_upload_dir
    )
    return path

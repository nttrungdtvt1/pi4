# # vision/camera_manager.py
# """
# Quản lý vòng đời camera.
# Hỗ trợ hai backend: picamera2 (Pi Camera) và opencv (USB cam như Logitech C170).
# Tự động chọn theo settings.camera_backend.
# """
# from __future__ import annotations

# import asyncio
# from typing import Optional

# import numpy as np

# from config.settings import settings
# from config.constants import CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS, CAMERA_WARMUP_SECONDS
# from logging_module.event_logger import log_app, log_event, EventType


# class CameraManager:
#     def __init__(self):
#         self._cam = None
#         self._active = False
#         self._backend = settings.camera_backend   # "picamera2" | "opencv"

#     # ── Lifecycle ──────────────────────────────────────────────────────────
#     async def camera_on(self) -> None:
#         if self._active:
#             return

#         loop = asyncio.get_running_loop()
#         # Chạy khởi động phần cứng trên ThreadPool để không block hệ thống
#         await loop.run_in_executor(None, self._init_camera)

#         # Chờ camera ổn định (cân bằng trắng, lấy nét)
#         await asyncio.sleep(CAMERA_WARMUP_SECONDS)

#         self._active = True
#         log_event(EventType.CAMERA_ON, backend=self._backend)

#     def _init_camera(self) -> None:
#         """Blocking — chạy trong thread pool."""
#         if self._backend == "picamera2":
#             self._init_picamera2()
#         else:
#             self._init_opencv()

#     def _init_picamera2(self) -> None:
#         try:
#             from picamera2 import Picamera2
#             cam = Picamera2()
#             config = cam.create_still_configuration(
#                 main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT), "format": "RGB888"}
#             )
#             cam.configure(config)
#             cam.start()
#             self._cam = cam
#         except Exception as exc:
#             log_app("error", "picamera2 init failed", detail=str(exc))
#             raise

#     def _init_opencv(self) -> None:
#         try:
#             import cv2
#             cam = cv2.VideoCapture(settings.camera_index)

#             # VÁ LỖI BUFFER LAG CHO WEBCAM USB: Ép buffer chỉ lưu 1 khung hình mới nhất
#             cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)

#             cam.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
#             cam.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
#             cam.set(cv2.CAP_PROP_FPS,          CAMERA_FPS)

#             if not cam.isOpened():
#                 raise RuntimeError(f"Cannot open camera index {settings.camera_index}")
#             self._cam = cam
#         except Exception as exc:
#             log_app("error", "OpenCV camera init failed", detail=str(exc))
#             raise

#     async def camera_off(self) -> None:
#         """Đẩy quá trình giải phóng I/O phần cứng sang ThreadPool để không block hệ thống."""
#         if not self._active:
#             return

#         # Set False ngay lập tức để block các lệnh capture_frame mới đang xếp hàng
#         self._active = False
#         loop = asyncio.get_running_loop()
#         await loop.run_in_executor(None, self._release_hardware)
#         log_event(EventType.CAMERA_OFF)

#     def _release_hardware(self) -> None:
#         """Blocking — tắt phần cứng."""
#         try:
#             if self._backend == "picamera2" and self._cam:
#                 self._cam.stop()
#                 self._cam.close()
#             elif self._cam:
#                 self._cam.release()
#         except Exception as exc:
#             log_app("warning", "Camera close error", detail=str(exc))
#         finally:
#             self._cam = None

#     # ── Capture ────────────────────────────────────────────────────────────
#     async def capture_frame(self) -> Optional[np.ndarray]:
#         """Chụp một frame → trả về mảng numpy (RGB)."""
#         if not self._active or self._cam is None:
#             log_app("warning", "capture_frame called but camera is off")
#             return None

#         loop = asyncio.get_running_loop()
#         return await loop.run_in_executor(None, self._read_frame)

#     def _read_frame(self) -> Optional[np.ndarray]:
#         try:
#             if self._backend == "picamera2":
#                 return self._cam.capture_array()   # Đã là định dạng RGB888 chuẩn
#             else:
#                 import cv2
#                 ret, frame = self._cam.read()

#                 # Khắc phục lỗi driver v4l2 đôi khi vẫn giữ frame rác dù đã set BUFFERSIZE=1
#                 # Grab thêm 1 frame nữa để chắc chắn đây là ảnh của giây phút hiện tại
#                 self._cam.grab()

#                 if not ret:
#                     log_app("warning", "OpenCV read() returned False (Camera disconnected?)")
#                     return None

#                 # OpenCV mặc định đọc BGR, phải chuyển sang RGB để đưa vào thuật toán nhận diện
#                 return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

#         except Exception as exc:
#             log_app("error", "Frame capture error", detail=str(exc))
#             return None

#     # ── Async context manager (Quản lý tài nguyên tự động bằng khối 'async with') ──
#     async def __aenter__(self) -> "CameraManager":
#         await self.camera_on()
#         return self

#     async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
#         await self.camera_off()

#     @property
#     def is_active(self) -> bool:
#         return self._active


# vision/camera_manager.py
"""
Quản lý vòng đời camera.
Hỗ trợ hai backend: picamera2 (Pi Camera) và opencv (USB cam như Logitech C170).
Tự động chọn theo settings.camera_backend.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import numpy as np

from config.settings import settings
from config.constants import CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS, CAMERA_WARMUP_SECONDS
from logging_module.event_logger import log_app, log_event, EventType


class CameraManager:
    def __init__(self):
        self._cam = None
        self._active = False
        self._backend = settings.camera_backend   # "picamera2" | "opencv"

    # ── Lifecycle ──────────────────────────────────────────────────────────
    async def camera_on(self) -> None:
        if self._active:
            return

        loop = asyncio.get_running_loop()
        # Chạy khởi động phần cứng trên ThreadPool để không block hệ thống
        await loop.run_in_executor(None, self._init_camera)

        # Chờ camera ổn định (cân bằng trắng, lấy nét)
        await asyncio.sleep(CAMERA_WARMUP_SECONDS)

        self._active = True
        log_event(EventType.CAMERA_ON, backend=self._backend)

    def _init_camera(self) -> None:
        """Blocking — chạy trong thread pool."""
        if self._backend == "picamera2":
            self._init_picamera2()
        else:
            self._init_opencv()

    def _init_picamera2(self) -> None:
        try:
            from picamera2 import Picamera2
            cam = Picamera2()
            config = cam.create_still_configuration(
                main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT), "format": "RGB888"}
            )
            cam.configure(config)
            cam.start()
            self._cam = cam
        except Exception as exc:
            log_app("error", "picamera2 init failed", detail=str(exc))
            raise

    def _init_opencv(self) -> None:
        try:
            import cv2
            cam = cv2.VideoCapture(settings.camera_index)

            # VÁ LỖI BUFFER LAG CHO WEBCAM USB: Ép buffer chỉ lưu 1 khung hình mới nhất
            cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            cam.set(cv2.CAP_PROP_FRAME_WIDTH,  CAMERA_WIDTH)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            cam.set(cv2.CAP_PROP_FPS,          CAMERA_FPS)

            if not cam.isOpened():
                raise RuntimeError(f"Cannot open camera index {settings.camera_index}")
            self._cam = cam
        except Exception as exc:
            log_app("error", "OpenCV camera init failed", detail=str(exc))
            raise

    async def camera_off(self) -> None:
        """Đẩy quá trình giải phóng I/O phần cứng sang ThreadPool để không block hệ thống."""
        if not self._active:
            return

        # Set False ngay lập tức để block các lệnh capture_frame mới đang xếp hàng
        self._active = False
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._release_hardware)
        log_event(EventType.CAMERA_OFF)

    def _release_hardware(self) -> None:
        """Blocking — tắt phần cứng."""
        try:
            if self._backend == "picamera2" and self._cam:
                self._cam.stop()
                self._cam.close()
            elif self._cam:
                self._cam.release()
        except Exception as exc:
            log_app("warning", "Camera close error", detail=str(exc))
        finally:
            self._cam = None

    # ── Capture ────────────────────────────────────────────────────────────
    async def capture_frame(self) -> Optional[np.ndarray]:
        """Chụp một frame → trả về mảng numpy (RGB)."""
        if not self._active or self._cam is None:
            log_app("warning", "capture_frame called but camera is off")
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_frame)

    def _read_frame(self) -> Optional[np.ndarray]:
        try:
            if self._backend == "picamera2":
                return self._cam.capture_array()   # Đã là định dạng RGB888 chuẩn
            else:
                import cv2
                ret, frame = self._cam.read()

                # Khắc phục lỗi driver v4l2 đôi khi vẫn giữ frame rác dù đã set BUFFERSIZE=1
                # Grab thêm 1 frame nữa để chắc chắn đây là ảnh của giây phút hiện tại
                self._cam.grab()

                if not ret:
                    log_app("warning", "OpenCV read() returned False (Camera disconnected?)")
                    return None

                # OpenCV mặc định đọc BGR, phải chuyển sang RGB để đưa vào thuật toán nhận diện
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        except Exception as exc:
            log_app("error", "Frame capture error", detail=str(exc))
            return None

    # ── Async context manager (Quản lý tài nguyên tự động bằng khối 'async with') ──
    async def __aenter__(self) -> "CameraManager":
        await self.camera_on()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.camera_off()

    @property
    def is_active(self) -> bool:
        return self._active

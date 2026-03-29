# # # config/settings.py
# # from __future__ import annotations
# # from pathlib import Path
# # from pydantic_settings import BaseSettings, SettingsConfigDict
# # from pydantic import Field, field_validator

# # # Thư mục gốc của project (raspberry_pi/)
# # BASE_DIR = Path(__file__).resolve().parent.parent

# # class Settings(BaseSettings):
# #     # ── UART ────────────────────────────────────────────────────────────
# #     uart_port:       str   = Field("/dev/ttyAMA0",  alias="UART_PORT")
# #     uart_baud:       int   = Field(115200,          alias="UART_BAUD")

# #     # ── Camera ──────────────────────────────────────────────────────────
# #     camera_index:    int   = Field(1,               alias="CAMERA_INDEX")
# #     camera_backend:  str   = Field("picamera2",     alias="CAMERA_BACKEND") # "picamera2" hoặc "opencv"

# #     # ── Face recognition (Moved here as single source of truth) ─────────
# #     face_tolerance:  float = Field(0.45,            alias="FACE_TOLERANCE")
# #     max_face_retry:  int   = Field(5,               alias="MAX_FACE_RETRY")
# #     encodings_path:  Path  = Field(
# #         default_factory=lambda: BASE_DIR / "data" / "known_faces.pkl",
# #         alias="ENCODINGS_PATH",
# #     )

# #     # ── Web server ──────────────────────────────────────────────────────
# #     api_server_url:  str   = Field("http://192.168.137.1:8000", alias="API_SERVER_URL")
# #     api_key:         str   = Field("change_me_api_key",         alias="API_KEY")

# #     # ── PIN sync security ───────────────────────────────────────────────
# #     hmac_secret_key: str   = Field("change_me_hmac_secret",     alias="HMAC_SECRET_KEY")

# #     # ── Internal log server (Pi tự serve file log) ───────────────────
# #     log_server_token: str  = Field("change_me_log_token",       alias="LOG_SERVER_TOKEN")
# #     log_server_port:  int  = Field(8001,                        alias="LOG_SERVER_PORT")

# #     # ── Cloud storage ───────────────────────────────────────────────────
# #     cloud_backend:   str   = Field("local",         alias="CLOUD_BACKEND") # "s3" | "cloudinary" | "local"
# #     cloud_bucket:    str   = Field("smart-door",    alias="CLOUD_BUCKET")
# #     cloud_key_id:    str   = Field("",              alias="CLOUD_KEY_ID")
# #     cloud_secret:    str   = Field("",              alias="CLOUD_SECRET")
# #     cloud_region:    str   = Field("ap-southeast-1",alias="CLOUD_REGION")

# #     # ── Paths ────────────────────────────────────────────────────────────
# #     captures_dir:    Path  = Field(
# #         default_factory=lambda: BASE_DIR / "data" / "captures",
# #         alias="CAPTURES_DIR",
# #     )
# #     temp_upload_dir: Path  = Field(
# #         default_factory=lambda: BASE_DIR / "data" / "temp_uploads",
# #         alias="TEMP_UPLOAD_DIR",
# #     )

# #     @field_validator("captures_dir", "temp_upload_dir", "encodings_path", mode="before")
# #     @classmethod
# #     def _ensure_path(cls, v):
# #         """Đảm bảo mọi đường dẫn sinh ra đều hợp lệ và gắn với BASE_DIR nếu là đường dẫn tương đối."""
# #         p = Path(v)
# #         if not p.is_absolute():
# #             return BASE_DIR / p
# #         return p

# #     # Nâng cấp lên SettingsConfigDict cho Pydantic V2
# #     model_config = SettingsConfigDict(
# #         env_file=str(BASE_DIR / ".env"),
# #         env_file_encoding="utf-8",
# #         populate_by_name=True,
# #         extra="ignore",
# #     )

# #     def ensure_dirs(self):
# #         """Tạo tất cả thư mục cần thiết nếu chưa tồn tại (chống lỗi FileNotFoundError)."""
# #         self.captures_dir.mkdir(parents=True, exist_ok=True)
# #         self.temp_upload_dir.mkdir(parents=True, exist_ok=True)
# #         self.encodings_path.parent.mkdir(parents=True, exist_ok=True)
# #         (BASE_DIR / "logging_module" / "logs").mkdir(parents=True, exist_ok=True)

# # # Singleton — import từ bất kỳ đâu đều dùng chung một instance
# # settings = Settings()




# # pi4/config/settings.py
# """
# Cấu hình hệ thống Smart Door Pi 4.
# Đọc từ file .env bằng python-dotenv.

# VERIFY: api_server_url and api_key must be set correctly for:
#   - face_sync_service: pull/push encodings
#   - presence_detector: broadcast scan frames to backend
#   - enroll_face: ACK backend after enrollment
# """
# from __future__ import annotations

# import os
# from pathlib import Path

# from dotenv import load_dotenv

# # Load .env from project root
# load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# class Settings:
#     # ── UART ─────────────────────────────────────────────────────────────────
#     @property
#     def uart_port(self) -> str:
#         return os.getenv("UART_PORT", "/dev/ttyAMA0")

#     @property
#     def uart_baud(self) -> int:
#         return int(os.getenv("UART_BAUD", "115200"))

#     # ── Camera ────────────────────────────────────────────────────────────────
#     @property
#     def camera_backend(self) -> str:
#         return os.getenv("CAMERA_BACKEND", "picamera2")

#     @property
#     def camera_index(self) -> int:
#         return int(os.getenv("CAMERA_INDEX", "0"))

#     # ── Face recognition ──────────────────────────────────────────────────────
#     @property
#     def face_tolerance(self) -> float:
#         return float(os.getenv("FACE_TOLERANCE", "0.45"))

#     @property
#     def max_face_retry(self) -> int:
#         return int(os.getenv("MAX_FACE_RETRY", "5"))

#     @property
#     def encodings_path(self) -> Path:
#         return Path(__file__).resolve().parent.parent / "data" / "known_faces.pkl"

#     # ── Backend connection ────────────────────────────────────────────────────
#     @property
#     def api_server_url(self) -> str:
#         """
#         URL của Backend FastAPI trên laptop.
#         Dùng trong:
#           - face_sync_service: pull pending encodings
#           - presence_detector: POST scan frames
#           - enroll_face: ACK pi_synced
#         """
#         return os.getenv("API_SERVER_URL", "http://192.168.137.1:8000")

#     @property
#     def api_key(self) -> str:
#         """
#         API key dùng để xác thực với Backend.
#         Phải khớp với PI_API_KEY trong backend .env.
#         Header: X-Pi-Api-Key
#         """
#         return os.getenv("API_KEY", "raspberry-pi-secret-key")

#     # ── Security ──────────────────────────────────────────────────────────────
#     @property
#     def hmac_secret_key(self) -> str:
#         return os.getenv("HMAC_SECRET_KEY", "change-me-hmac-secret")

#     # ── Cloud ─────────────────────────────────────────────────────────────────
#     @property
#     def cloud_backend(self) -> str:
#         return os.getenv("CLOUD_BACKEND", "local")

#     # ── Paths ─────────────────────────────────────────────────────────────────
#     @property
#     def captures_dir(self) -> Path:
#         return Path(__file__).resolve().parent.parent / "data" / "captures"

#     @property
#     def temp_uploads_dir(self) -> Path:
#         return Path(__file__).resolve().parent.parent / "data" / "temp_uploads"

#     @property
#     def dataset_dir(self) -> Path:
#         """Root directory for enrollment dataset images."""
#         return Path(__file__).resolve().parent.parent / "data" / "dataset"

#     def ensure_dirs(self) -> None:
#         """Create all required data directories if they don't exist."""
#         dirs = [
#             self.captures_dir,
#             self.temp_uploads_dir,
#             self.dataset_dir,
#             self.encodings_path.parent,
#         ]
#         for d in dirs:
#             d.mkdir(parents=True, exist_ok=True)


# settings = Settings()

# pi4/config/settings.py
"""
Cấu hình hệ thống Smart Door Pi 4.
Đọc từ file .env bằng python-dotenv.

Đã fix lỗi thiếu biến (temp_upload_dir, cloud_bucket, cloud_key_id...)
để cloud_uploader không bị crash khi upload.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Settings:
    # ── UART ─────────────────────────────────────────────────────────────────
    @property
    def uart_port(self) -> str:
        return os.getenv("UART_PORT", "/dev/ttyAMA0")

    @property
    def uart_baud(self) -> int:
        return int(os.getenv("UART_BAUD", "115200"))

    # ── Camera ────────────────────────────────────────────────────────────────
    @property
    def camera_backend(self) -> str:
        return os.getenv("CAMERA_BACKEND", "picamera2")

    @property
    def camera_index(self) -> int:
        return int(os.getenv("CAMERA_INDEX", "0"))

    # ── Face recognition ──────────────────────────────────────────────────────
    @property
    def face_tolerance(self) -> float:
        return float(os.getenv("FACE_TOLERANCE", "0.45"))

    @property
    def max_face_retry(self) -> int:
        return int(os.getenv("MAX_FACE_RETRY", "5"))

    @property
    def encodings_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "data" / "known_faces.pkl"

    # ── Backend connection ────────────────────────────────────────────────────
    @property
    def api_server_url(self) -> str:
        return os.getenv("API_SERVER_URL", "http://192.168.137.1:8000")

    @property
    def api_key(self) -> str:
        return os.getenv("API_KEY", "raspberry-pi-secret-key")

    # ── Security ──────────────────────────────────────────────────────────────
    @property
    def hmac_secret_key(self) -> str:
        return os.getenv("HMAC_SECRET_KEY", "change-me-hmac-secret")

    # ── Cloud ─────────────────────────────────────────────────────────────────
    @property
    def cloud_backend(self) -> str:
        return os.getenv("CLOUD_BACKEND", "local")

    @property
    def cloud_bucket(self) -> str:
        return os.getenv("CLOUD_BUCKET", "smart-door")

    @property
    def cloud_key_id(self) -> str:
        return os.getenv("CLOUD_KEY_ID", "")

    @property
    def cloud_secret(self) -> str:
        return os.getenv("CLOUD_SECRET", "")

    @property
    def cloud_region(self) -> str:
        return os.getenv("CLOUD_REGION", "ap-southeast-1")

    # ── Paths ─────────────────────────────────────────────────────────────────
    @property
    def captures_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "data" / "captures"

    # FIX: Đã đổi thành temp_upload_dir (bỏ chữ s) để đồng bộ với các module khác
    @property
    def temp_upload_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "data" / "temp_uploads"

    @property
    def dataset_dir(self) -> Path:
        """Root directory for enrollment dataset images."""
        return Path(__file__).resolve().parent.parent / "data" / "dataset"

    def ensure_dirs(self) -> None:
        """Create all required data directories if they don't exist."""
        dirs = [
            self.captures_dir,
            self.temp_upload_dir,
            self.dataset_dir,
            self.encodings_path.parent,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()

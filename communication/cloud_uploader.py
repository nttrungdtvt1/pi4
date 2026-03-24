# # communication/cloud_uploader.py
# """
# Upload ảnh lên cloud storage.
# Hỗ trợ: AWS S3 | Cloudinary | local (dev mode).
# Được tối ưu để chạy Non-blocking (Thread Pool) trên Raspberry Pi.
# """
# from __future__ import annotations

# import asyncio
# import shutil
# from pathlib import Path
# from typing import Optional

# from config.settings import settings
# from logging_module.event_logger import log_event, log_app, EventType

# # ── Backend implementations (Synchronous - Chạy trong ThreadPool) ────

# def _upload_s3(path: Path) -> str:
#     import boto3
#     s3 = boto3.client(
#         "s3",
#         aws_access_key_id=settings.cloud_key_id,
#         aws_secret_access_key=settings.cloud_secret,
#         region_name=settings.cloud_region,
#     )
#     key = f"smart-door/captures/{path.name}"
#     s3.upload_file(
#         str(path),
#         settings.cloud_bucket,
#         key,
#         ExtraArgs={"ContentType": "image/jpeg", "ACL": "public-read"}
#     )
#     return f"https://{settings.cloud_bucket}.s3.{settings.cloud_region}.amazonaws.com/{key}"


# def _upload_cloudinary(path: Path) -> str:
#     import cloudinary
#     import cloudinary.uploader
#     cloudinary.config(
#         cloud_name=settings.cloud_bucket,
#         api_key=settings.cloud_key_id,
#         api_secret=settings.cloud_secret,
#     )
#     # resource_type="image" giúp Cloudinary tự động tối ưu hóa file
#     result = cloudinary.uploader.upload(
#         str(path),
#         folder="smart-door/captures",
#         resource_type="image"
#     )
#     return result["secure_url"]


# def _upload_local(path: Path) -> str:
#     """Dev mode: copy vào thư mục local và trả về đường dẫn tuyệt đối."""
#     dest = settings.captures_dir / path.name
#     settings.captures_dir.mkdir(parents=True, exist_ok=True)

#     # Kiểm tra tránh lỗi tự copy đè lên chính nó (SameFileError)
#     if path.resolve() != dest.resolve():
#         shutil.copy2(path, dest)
#     return f"file://{dest.absolute()}"


# # Tách Dictionary Map ra ngoài để không phải tạo lại mỗi lần gọi hàm upload
# UPLOAD_STRATEGIES = {
#     "s3": _upload_s3,
#     "cloudinary": _upload_cloudinary,
#     "local": _upload_local
# }

# # ── Public API (Asynchronous - An toàn cho Event Loop) ───────────────

# async def upload(path: Path) -> Optional[str]:
#     """
#     Upload file ảnh lên cloud storage (Non-blocking).
#     Trả về public URL hoặc None nếu thất bại.
#     Tự động xóa file temp sau khi upload thành công để giải phóng thẻ nhớ.
#     """
#     if not path or not path.exists():
#         log_app("warning", f"Upload failed: File not found -> {path}")
#         return None

#     loop = asyncio.get_running_loop()
#     backend = settings.cloud_backend.lower()

#     # Fallback an toàn về local nếu file .env ghi sai tên backend
#     upload_fn = UPLOAD_STRATEGIES.get(backend, _upload_local)

#     try:
#         # Đẩy I/O nặng ra ThreadPool phụ, không làm đơ Camera hay UART
#         url = await loop.run_in_executor(None, upload_fn, path)

#         # Cải tiến: Chỉ xóa nếu file nằm trong cây thư mục temp
#         if settings.temp_upload_dir in path.parents:
#             path.unlink(missing_ok=True)
#             log_app("debug", f"Deleted temp file: {path.name}")

#         log_event(EventType.CLOUD_UPLOAD_OK, url=url, backend=backend)
#         return url

#     except Exception as exc:
#         log_event(EventType.CLOUD_UPLOAD_FAIL, detail=str(exc), file=path.name)
#         log_app("error", f"Upload to {backend} failed: {exc}")
#         return None


# async def upload_pending() -> None:
#     """
#     Retry ảnh còn sót trong temp_uploads/ chưa upload thành công.
#     Gọi lúc Pi khởi động lại (startup) sau khi mất điện/mất mạng.
#     """
#     if not settings.temp_upload_dir.exists():
#         return

#     pending_files = list(settings.temp_upload_dir.glob("*.jpg"))
#     if not pending_files:
#         return

#     log_app("info", f"Found {len(pending_files)} pending images. Retrying uploads...")

#     # Cải tiến: Upload tuần tự và có nhịp nghỉ để tránh Pi bị tràn RAM/Nghẽn mạng lúc khởi động
#     for path in pending_files:
#         await upload(path)
#         await asyncio.sleep(0.5) # Nghỉ 0.5s giữa các bức ảnh

#     log_app("info", "Finished processing pending uploads.")



# communication/cloud_uploader.py
"""
Upload ảnh lên cloud storage.
Hỗ trợ: AWS S3 | Cloudinary | local (dev mode).
Được tối ưu để chạy Non-blocking (Thread Pool) trên Raspberry Pi.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Optional

from config.settings import settings
from logging_module.event_logger import log_event, log_app, EventType

# ── Backend implementations (Synchronous - Chạy trong ThreadPool) ────

def _upload_s3(path: Path) -> str:
    import boto3
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.cloud_key_id,
        aws_secret_access_key=settings.cloud_secret,
        region_name=settings.cloud_region,
    )
    key = f"smart-door/captures/{path.name}"
    s3.upload_file(
        str(path),
        settings.cloud_bucket,
        key,
        ExtraArgs={"ContentType": "image/jpeg", "ACL": "public-read"}
    )
    return f"https://{settings.cloud_bucket}.s3.{settings.cloud_region}.amazonaws.com/{key}"


def _upload_cloudinary(path: Path) -> str:
    import cloudinary
    import cloudinary.uploader
    cloudinary.config(
        cloud_name=settings.cloud_bucket,
        api_key=settings.cloud_key_id,
        api_secret=settings.cloud_secret,
    )
    # resource_type="image" giúp Cloudinary tự động tối ưu hóa file
    result = cloudinary.uploader.upload(
        str(path),
        folder="smart-door/captures",
        resource_type="image"
    )
    return result["secure_url"]


def _upload_local(path: Path) -> str:
    """Dev mode: copy vào thư mục local và trả về đường dẫn tuyệt đối."""
    dest = settings.captures_dir / path.name
    settings.captures_dir.mkdir(parents=True, exist_ok=True)

    # Kiểm tra tránh lỗi tự copy đè lên chính nó (SameFileError)
    if path.resolve() != dest.resolve():
        shutil.copy2(path, dest)
    return f"file://{dest.absolute()}"


# Tách Dictionary Map ra ngoài để không phải tạo lại mỗi lần gọi hàm upload
UPLOAD_STRATEGIES = {
    "s3": _upload_s3,
    "cloudinary": _upload_cloudinary,
    "local": _upload_local
}

# ── Public API (Asynchronous - An toàn cho Event Loop) ───────────────

async def upload(path: Path) -> Optional[str]:
    """
    Upload file ảnh lên cloud storage (Non-blocking).
    Trả về public URL hoặc None nếu thất bại.
    Tự động xóa file temp sau khi upload thành công để giải phóng thẻ nhớ.
    """
    if not path or not path.exists():
        log_app("warning", f"Upload failed: File not found -> {path}")
        return None

    loop = asyncio.get_running_loop()
    backend = settings.cloud_backend.lower()

    # Fallback an toàn về local nếu file .env ghi sai tên backend
    upload_fn = UPLOAD_STRATEGIES.get(backend, _upload_local)

    try:
        # Đẩy I/O nặng ra ThreadPool phụ, không làm đơ Camera hay UART
        url = await loop.run_in_executor(None, upload_fn, path)

        # Cải tiến: Chỉ xóa nếu file nằm trong cây thư mục temp
        if settings.temp_upload_dir in path.parents:
            path.unlink(missing_ok=True)
            log_app("debug", f"Deleted temp file: {path.name}")

        log_event(EventType.CLOUD_UPLOAD_OK, url=url, backend=backend)
        return url

    except Exception as exc:
        log_event(EventType.CLOUD_UPLOAD_FAIL, detail=str(exc), file=path.name)
        log_app("error", f"Upload to {backend} failed: {exc}")
        return None


async def upload_pending() -> None:
    """
    Retry ảnh còn sót trong temp_uploads/ chưa upload thành công.
    Gọi lúc Pi khởi động lại (startup) sau khi mất điện/mất mạng.
    """
    if not settings.temp_upload_dir.exists():
        return

    pending_files = list(settings.temp_upload_dir.glob("*.jpg"))
    if not pending_files:
        return

    log_app("info", f"Found {len(pending_files)} pending images. Retrying uploads...")

    # Cải tiến: Upload tuần tự và có nhịp nghỉ để tránh Pi bị tràn RAM/Nghẽn mạng lúc khởi động
    for path in pending_files:
        await upload(path)
        await asyncio.sleep(0.5) # Nghỉ 0.5s giữa các bức ảnh

    log_app("info", "Finished processing pending uploads.")

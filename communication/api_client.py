# # communication/api_client.py
# from __future__ import annotations

# import asyncio
# from datetime import datetime
# from typing import Optional, Any
# import aiohttp

# from config.settings import settings
# from config.constants import API_TIMEOUT, API_RETRY_ATTEMPTS, API_HEARTBEAT_INTERVAL
# from logging_module.event_logger import log_app, log_event, EventType

# # Khuyến nghị: Trong main.py, nếu có thể hãy khởi tạo một aiohttp.ClientSession global
# # Tuy nhiên, đối với ứng dụng chạy nền dạng này, cách làm hiện tại vẫn chấp nhận được.

# def _headers() -> dict[str, str]:
#     return {
#         "Authorization": f"Bearer {settings.api_key}",
#         "Content-Type":  "application/json",
#     }

# async def _post(endpoint: str, payload: dict) -> Optional[dict]:
#     url = f"{settings.api_server_url}{endpoint}"
#     for attempt in range(1, API_RETRY_ATTEMPTS + 1):
#         try:
#             async with aiohttp.ClientSession() as session:
#                 async with session.post(
#                     url, json=payload, headers=_headers(),
#                     timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
#                 ) as resp:
#                     if resp.status in (200, 201):
#                         return await resp.json()
#                     log_app("warning", f"POST {endpoint} status={resp.status}", attempt=attempt)
#         except Exception as exc:
#             log_event(EventType.API_ERROR, endpoint=endpoint, detail=str(exc), attempt=attempt)

#         if attempt < API_RETRY_ATTEMPTS:
#             await asyncio.sleep(1.5 * attempt) # Exponential backoff
#     return None

# async def _get(endpoint: str) -> Optional[dict]:
#     url = f"{settings.api_server_url}{endpoint}"
#     try:
#         async with aiohttp.ClientSession() as session:
#             async with session.get(
#                 url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
#             ) as resp:
#                 if resp.status == 200:
#                     return await resp.json()
#     except Exception as exc:
#         log_event(EventType.API_ERROR, endpoint=endpoint, detail=str(exc))
#     return None

# # ── Public API ─────────────────────────────────────────────────────────────
# async def post_access_log(name: Optional[str], method: str, success: bool, image_url: str = "") -> None:
#     await _post("/api/events/", {
#         "type": "access", "name": name or "unknown", "method": method,
#         "success": success, "image_url": image_url, "timestamp": datetime.now().isoformat(),
#     })

# async def post_event(event_type: str, **data: Any) -> None:
#     await _post("/api/events/", {
#         "type": event_type, "timestamp": datetime.now().isoformat(), **data,
#     })

# async def post_alarm(reason: str, image_url: str = "") -> None:
#     await post_event("alarm", reason=reason, image_url=image_url)

# async def get_pending_command() -> Optional[str]:
#     resp = await _get("/api/device/pending-command/")
#     if resp and isinstance(resp.get("command"), str):
#         return resp["command"]
#     return None

# async def get_pending_pin() -> Optional[str]:
#     """Lấy PIN mới nếu Web yêu cầu đổi PIN."""
#     resp = await _get("/api/device/pending-pin/")
#     if resp and isinstance(resp.get("pin"), str):
#         return resp["pin"]
#     return None

# async def heartbeat_loop() -> None:
#     log_app("info", "Heartbeat loop started")
#     while True:
#         try:
#             await _post("/api/device/heartbeat/", {
#                 "timestamp": datetime.now().isoformat(), "status": "online",
#             })
#         except asyncio.CancelledError:
#             raise
#         except Exception as exc:
#             log_event(EventType.API_ERROR, detail=str(exc), phase="heartbeat")
#         await asyncio.sleep(API_HEARTBEAT_INTERVAL)


# communication/api_client.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, Any
import aiohttp

from config.settings import settings
from config.constants import API_TIMEOUT, API_RETRY_ATTEMPTS, API_HEARTBEAT_INTERVAL
from logging_module.event_logger import log_app, log_event, EventType

# Khuyến nghị: Trong main.py, nếu có thể hãy khởi tạo một aiohttp.ClientSession global
# Tuy nhiên, đối với ứng dụng chạy nền dạng này, cách làm hiện tại vẫn chấp nhận được.

def _headers() -> dict[str, str]:
    return {
        # "Authorization": f"Bearer {settings.api_key}",
        # "Content-Type":  "application/json",
        "X-Pi-Api-Key": settings.api_key,  # Chìa khóa để Web Backend cho phép Pi đi vào
        "Content-Type": "application/json",
    }

async def _post(endpoint: str, payload: dict) -> Optional[dict]:
    url = f"{settings.api_server_url}{endpoint}"
    for attempt in range(1, API_RETRY_ATTEMPTS + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=_headers(),
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
                ) as resp:
                    if resp.status in (200, 201):
                        return await resp.json()
                    log_app("warning", f"POST {endpoint} status={resp.status}", attempt=attempt)
        except Exception as exc:
            log_event(EventType.API_ERROR, endpoint=endpoint, detail=str(exc), attempt=attempt)

        if attempt < API_RETRY_ATTEMPTS:
            await asyncio.sleep(1.5 * attempt) # Exponential backoff
    return None

async def _get(endpoint: str) -> Optional[dict]:
    url = f"{settings.api_server_url}{endpoint}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=_headers(), timeout=aiohttp.ClientTimeout(total=API_TIMEOUT),
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as exc:
        log_event(EventType.API_ERROR, endpoint=endpoint, detail=str(exc))
    return None

# ── Public API ─────────────────────────────────────────────────────────────

async def post_access_log(name: Optional[str], method: str, success: bool, image_url: str = "") -> None:
    # 1. Xác định type chuẩn xác theo Backend yêu cầu
    if method == "face":
        event_type = "face_recognized" if success else "face_unknown"
    else:
        event_type = "pin_correct" if success else "pin_wrong"

    # 2. Gói các dữ liệu phụ (name, method, success) vào trong dict "payload"
    data_to_send = {
        "type": event_type,
        "image_url": image_url,
        "payload": {
            "name": name if name else "unknown",
            "method": method,
            "success": success
        },
        "timestamp": datetime.now().isoformat(),
    }
    await _post("/api/events/", data_to_send)

async def post_event(event_type: str, **data: Any) -> None:
    # Gom các tham số data thừa vào đúng trường "payload"
    await _post("/api/events/", {
        "type": event_type,
        "payload": data,
        "timestamp": datetime.now().isoformat(),
    })

async def post_alarm(reason: str, image_url: str = "") -> None:
    # Backend quy định type cảnh báo là "alarm_triggered"
    await _post("/api/events/", {
        "type": "alarm_triggered",
        "image_url": image_url,
        "payload": {"reason": reason},
        "timestamp": datetime.now().isoformat(),
    })

async def get_pending_command() -> Optional[str]:
    resp = await _get("/api/device/pending-command/")
    if resp and isinstance(resp.get("command"), str):
        return resp["command"]
    return None

async def get_pending_pin() -> Optional[str]:
    """Lấy PIN mới nếu Web yêu cầu đổi PIN."""
    resp = await _get("/api/device/pending-pin/")
    # SỬA LỖI CẢNH BÁO SỐ 3: Backend trả về danh sách pending_pins, không phải chuỗi pin
    if resp and "pending_pins" in resp and isinstance(resp["pending_pins"], list):
        if len(resp["pending_pins"]) > 0:
            return str(resp["pending_pins"][0]) # Lấy mã PIN đầu tiên trong mảng
    return None

async def ack_pin_sync() -> bool:
    """
    Báo cáo Backend rằng PIN đã được đồng bộ thành công xuống STM32.
    Backend sẽ xóa pin_plaintext và đánh dấu pi_synced = True.
    """
    resp = await _post("/api/device/ack-pin/", {})
    if resp and resp.get("success"):
        log_app("info", "ACK sent to Backend — PIN sync acknowledged")
        return True
    log_app("warning", "Failed to send ACK to Backend", response=resp)
    return False

async def heartbeat_loop() -> None:
    log_app("info", "Heartbeat loop started")
    while True:
        try:
            await _post("/api/device/heartbeat/", {
                "timestamp": datetime.now().isoformat(),
                "status": "online",
            })
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_event(EventType.API_ERROR, detail=str(exc), phase="heartbeat")
        await asyncio.sleep(API_HEARTBEAT_INTERVAL)

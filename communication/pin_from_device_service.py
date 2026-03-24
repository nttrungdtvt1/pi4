# communication/pin_from_device_service.py
import asyncio
import re
import aiohttp

from config.settings import settings
from logging_module.event_logger import log_app, log_event, EventType

_PIN_ENDPOINT = "/api/device/pin"
_MAX_RETRIES = 5
_BACKOFF_BASE = 2.0
_PIN_PATTERN = re.compile(r'^\d{6}$')

async def _async_push_pin(pin: str) -> bool:
    """Đẩy mã PIN mới từ thiết bị lên Backend bằng aiohttp (Không gây nghẽn)"""
    url = f"{settings.api_server_url.rstrip('/')}{_PIN_ENDPOINT}"
    headers = {"X-Pi-Api-Key": settings.api_key, "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=10)

    # Mở một session bất đồng bộ để gửi API
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with session.put(url, json={"pin": pin, "source": "device"}, headers=headers) as resp:
                    if resp.status in (200, 201):
                        log_app("info", f"PIN pushed to backend successfully (attempt {attempt})")
                        return True
                    if 400 <= resp.status < 500:
                        error_text = await resp.text()
                        log_app("error", f"Backend rejected PIN (HTTP {resp.status}): {error_text[:200]}")
                        return False

                    log_app("warning", f"Backend error (HTTP {resp.status}), attempt {attempt}/{_MAX_RETRIES}")
            except asyncio.TimeoutError:
                log_app("warning", f"Request timeout, attempt {attempt}/{_MAX_RETRIES}")
            except Exception as exc:
                log_app("warning", f"Request error: {exc}, attempt {attempt}/{_MAX_RETRIES}")

            # Chờ theo cấp số nhân (Exponential Backoff) mà không làm block hệ thống
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))

    return False

class PinFromDeviceService:
    def __init__(self, pin_from_device_queue: asyncio.Queue[str]):
        self._queue = pin_from_device_queue

    async def run(self) -> None:
        log_app("info", "PinFromDeviceService started")
        while True:
            try:
                new_pin: str = await self._queue.get()
                if _PIN_PATTERN.match(new_pin):
                    # Gọi trực tiếp hàm Async thay vì phải dùng Threading/Executor như cũ
                    success = await _async_push_pin(new_pin)

                    if success:
                        log_event(EventType.PIN_SYNCED, source="device→backend")
                    else:
                        log_event(EventType.PIN_SYNC_FAILED, source="device→backend", detail="HTTP push failed")
                self._queue.task_done()

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log_event(EventType.SYSTEM_ERROR, detail=f"PinService error: {exc}")
                await asyncio.sleep(1)

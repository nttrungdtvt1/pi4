# # tests/test_api_client.py
# """
# Tests cho api_client.
# Mock aiohttp.ClientSession để giả lập các HTTP requests (GET, POST),
# kiểm tra logic sinh payload và retry timeout.
# """
# import sys
# from pathlib import Path
# sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# import asyncio
# import pytest
# from unittest.mock import patch, MagicMock, AsyncMock

# from communication.api_client import (
#     _post, _get, get_pending_command, post_access_log
# )
# from config.settings import settings

# # --- Helper classes để mock aiohttp context manager (async with) ---
# class MockResponse:
#     def __init__(self, status_code, json_data=None):
#         self.status = status_code
#         self._json_data = json_data or {}

#     async def json(self):
#         return self._json_data

#     async def __aenter__(self):
#         return self

#     async def __aexit__(self, *args):
#         pass


# @pytest.mark.asyncio
# class TestApiClient:
#     @patch("aiohttp.ClientSession.post")
#     async def test_post_success(self, mock_post):
#         """Kiểm tra POST thành công (HTTP 200)."""
#         mock_post.return_value = MockResponse(200, {"status": "ok"})

#         result = await _post("/test-endpoint", {"data": 123})

#         assert result == {"status": "ok"}
#         mock_post.assert_called_once()
#         # Xác minh URL gửi đi là chuẩn
#         args, kwargs = mock_post.call_args
#         assert args[0] == f"{settings.api_server_url}/test-endpoint"
#         assert kwargs["json"] == {"data": 123}

#     @patch("asyncio.sleep", new_callable=AsyncMock)  # Bỏ qua thời gian sleep
#     @patch("aiohttp.ClientSession.post")
#     async def test_post_retry_on_failure(self, mock_post, mock_sleep):
#         """Kiểm tra logic thử lại (retry) khi mạng bị lỗi (HTTP 500)."""
#         # Trả về lỗi 500 liên tục
#         mock_post.return_value = MockResponse(500)

#         from config.constants import API_RETRY_ATTEMPTS
#         result = await _post("/test-endpoint", {})

#         assert result is None  # Cuối cùng vẫn thất bại
#         assert mock_post.call_count == API_RETRY_ATTEMPTS  # Phải thử lại đủ số lần quy định
#         assert mock_sleep.call_count == API_RETRY_ATTEMPTS - 1

#     @patch("aiohttp.ClientSession.get")
#     async def test_get_pending_command(self, mock_get):
#         """Kiểm tra hàm lấy lệnh từ dashboard parse đúng JSON."""
#         # Giả lập web trả về lệnh CMD_STOP_ALARM
#         mock_get.return_value = MockResponse(200, {"command": "CMD_STOP_ALARM"})

#         cmd = await get_pending_command()

#         assert cmd == "CMD_STOP_ALARM"

#     @patch("aiohttp.ClientSession.get")
#     async def test_get_pending_command_empty(self, mock_get):
#         """Kiểm tra hàm xử lý đúng khi web không có lệnh nào (trả về rỗng)."""
#         mock_get.return_value = MockResponse(200, {"command": None})
#         cmd = await get_pending_command()
#         assert cmd is None

#     @patch("communication.api_client._post", new_callable=AsyncMock)
#     async def test_post_access_log_payload(self, mock_private_post):
#         """Kiểm tra cấu trúc dữ liệu gửi lên log_access."""
#         await post_access_log(name="Alice", method="face", success=True, image_url="http://img")

#         mock_private_post.assert_called_once()
#         args, kwargs = mock_private_post.call_args
#         assert args[0] == "/api/events/"
#         payload = args[1]
#         assert payload["type"] == "access"
#         assert payload["name"] == "Alice"
#         assert payload["success"] is True
#         assert "timestamp" in payload



# tests/test_api_client.py
"""
Tests cho api_client.
Mock aiohttp.ClientSession để giả lập các HTTP requests (GET, POST),
kiểm tra logic sinh payload và retry timeout.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from communication.api_client import (
    _post, _get, get_pending_command, post_access_log
)
from config.settings import settings

# --- Helper classes để mock aiohttp context manager (async with) ---
class MockResponse:
    def __init__(self, status_code, json_data=None):
        self.status = status_code
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
class TestApiClient:
    @patch("aiohttp.ClientSession.post")
    async def test_post_success(self, mock_post):
        """Kiểm tra POST thành công (HTTP 200)."""
        mock_post.return_value = MockResponse(200, {"status": "ok"})

        result = await _post("/test-endpoint", {"data": 123})

        assert result == {"status": "ok"}
        mock_post.assert_called_once()
        # Xác minh URL gửi đi là chuẩn
        args, kwargs = mock_post.call_args
        assert args[0] == f"{settings.api_server_url}/test-endpoint"
        assert kwargs["json"] == {"data": 123}

    @patch("asyncio.sleep", new_callable=AsyncMock)  # Bỏ qua thời gian sleep
    @patch("aiohttp.ClientSession.post")
    async def test_post_retry_on_failure(self, mock_post, mock_sleep):
        """Kiểm tra logic thử lại (retry) khi mạng bị lỗi (HTTP 500)."""
        # Trả về lỗi 500 liên tục
        mock_post.return_value = MockResponse(500)

        from config.constants import API_RETRY_ATTEMPTS
        result = await _post("/test-endpoint", {})

        assert result is None  # Cuối cùng vẫn thất bại
        assert mock_post.call_count == API_RETRY_ATTEMPTS  # Phải thử lại đủ số lần quy định
        assert mock_sleep.call_count == API_RETRY_ATTEMPTS - 1

    @patch("aiohttp.ClientSession.get")
    async def test_get_pending_command(self, mock_get):
        """Kiểm tra hàm lấy lệnh từ dashboard parse đúng JSON."""
        # Giả lập web trả về lệnh CMD_STOP_ALARM
        mock_get.return_value = MockResponse(200, {"command": "CMD_STOP_ALARM"})

        cmd = await get_pending_command()

        assert cmd == "CMD_STOP_ALARM"

    @patch("aiohttp.ClientSession.get")
    async def test_get_pending_command_empty(self, mock_get):
        """Kiểm tra hàm xử lý đúng khi web không có lệnh nào (trả về rỗng)."""
        mock_get.return_value = MockResponse(200, {"command": None})
        cmd = await get_pending_command()
        assert cmd is None

    @patch("communication.api_client._post", new_callable=AsyncMock)
    async def test_post_access_log_payload(self, mock_private_post):
        """Kiểm tra cấu trúc dữ liệu gửi lên log_access."""
        await post_access_log(name="Alice", method="face", success=True, image_url="http://img")

        mock_private_post.assert_called_once()
        args, kwargs = mock_private_post.call_args
        assert args[0] == "/api/events/"
        payload = args[1]
        assert payload["type"] == "access"
        assert payload["name"] == "Alice"
        assert payload["success"] is True
        assert "timestamp" in payload

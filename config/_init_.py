# config/__init__.py
"""
Facade/Lễ tân của package config.
Gom các module lại để các file khác import ngắn gọn hơn.
Ví dụ: from config import settings, constants
"""
from .settings import settings
from . import constants

# Giới hạn những gì được export ra khi dùng lệnh `from config import *`
__all__ = ["settings", "constants"]

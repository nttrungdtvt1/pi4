# # config/constants.py
# """
# Hằng số cố định vật lý hoặc giao thức.
# KHÔNG phụ thuộc môi trường (dev/prod).
# Mọi file trong dự án cần giá trị cứng (hardcode) đều phải import từ đây.
# """

# # ── Face Recognition (Static params) ──────────────────────────────────────
# FACE_CAPTURE_DELAY = 0.4        # Giây chờ giữa các lần capture khi retry

# # ── Cửa & relay ───────────────────────────────────────────────────────────
# DOOR_OPEN_SECONDS = 10          # Relay giữ mở bao lâu (giây)

# # ── Alarm ─────────────────────────────────────────────────────────────────
# ALARM_DURATION_SECONDS = 180    # Thời gian còi kêu tối đa (3 phút = 180s)
# MAX_PASSWORD_ATTEMPTS = 3       # Số lần nhập sai PIN trước khi kích hoạt báo động

# # ── UART ──────────────────────────────────────────────────────────────────
# UART_READ_TIMEOUT = 1.0         # Giây timeout khi đọc serial
# UART_SEND_RETRY = 3             # Số lần thử gửi lại nếu không nhận được ACK
# UART_ACK_TIMEOUT = 3.0          # Giây chờ STM32 phản hồi ACK sau khi gửi lệnh

# # ── Commands gửi xuống STM32 ──────────────────────────────────────────────
# CMD_UNLOCK_DOOR = "CMD_UNLOCK_DOOR"
# CMD_ENABLE_KEYPAD = "CMD_ENABLE_KEYPAD"
# CMD_STOP_ALARM = "CMD_STOP_ALARM"
# CMD_SET_PIN = "CMD_SET_PIN"     # Lệnh cài PIN: CMD_SET_PIN + space + HMAC hex

# # ── Responses/Events từ STM32 ─────────────────────────────────────────────
# EVT_MOTION_DETECTED = "EVENT_MOTION_DETECTED"
# RSP_DOOR_OPENED = "DOOR_OPENED"
# RSP_DOOR_OPENED_PWD = "DOOR_OPENED_PASSWORD"
# RSP_PASSWORD_FAILED = "PASSWORD_FAILED"
# RSP_ALARM_ACTIVE = "ALARM_ACTIVE"
# RSP_ACK_PIN_SET = "ACK_PIN_SET"

# # ── Log rotation ──────────────────────────────────────────────────────────
# LOG_MAX_BYTES = 5_000_000       # Giới hạn 5 MB mỗi file log
# LOG_BACKUP_COUNT = 5            # Giữ lại 5 bản cũ → Tối đa chiếm ~30 MB trên SD card

# # ── Camera ────────────────────────────────────────────────────────────────
# CAMERA_WIDTH = 640              # Chiều rộng khung hình
# CAMERA_HEIGHT = 480             # Chiều cao khung hình (VGA là tối ưu nhất cho Pi 4)
# CAMERA_FPS = 15                 # Số khung hình/giây
# CAMERA_WARMUP_SECONDS = 1.5     # Thời gian chờ cảm biến camera ổn định độ sáng (Auto Exposure)

# # ── API ───────────────────────────────────────────────────────────────────
# API_HEARTBEAT_INTERVAL = 30     # Giây giữa mỗi lần ping báo cáo "Online" về server
# API_TIMEOUT = 8                 # Giây timeout cho mỗi HTTP request
# API_RETRY_ATTEMPTS = 3          # Số lần thử lại API khi rớt mạng

# # ── Cloud upload ──────────────────────────────────────────────────────────
# UPLOAD_MAX_SIZE_MB = 5          # Dung lượng tối đa mỗi file ảnh upload
# UPLOAD_QUALITY = 85             # Chất lượng nén JPEG (0-100) để tiết kiệm băng thông



# config/constants.py
"""
Hằng số cố định vật lý hoặc giao thức.
KHÔNG phụ thuộc môi trường (dev/prod).
Mọi file trong dự án cần giá trị cứng (hardcode) đều phải import từ đây.
"""

# ── Face Recognition (Static params) ──────────────────────────────────────
FACE_CAPTURE_DELAY = 0.4        # Giây chờ giữa các lần capture khi retry

# ── Cửa & relay ───────────────────────────────────────────────────────────
DOOR_OPEN_SECONDS = 10          # Relay giữ mở bao lâu (giây)

# ── Alarm ─────────────────────────────────────────────────────────────────
ALARM_DURATION_SECONDS = 180    # Thời gian còi kêu tối đa (3 phút = 180s)
MAX_PASSWORD_ATTEMPTS = 3       # Số lần nhập sai PIN trước khi kích hoạt báo động

# ── UART ──────────────────────────────────────────────────────────────────
UART_READ_TIMEOUT = 1.0         # Giây timeout khi đọc serial
UART_SEND_RETRY = 3             # Số lần thử gửi lại nếu không nhận được ACK
UART_ACK_TIMEOUT = 3.0          # Giây chờ STM32 phản hồi ACK sau khi gửi lệnh

# ── Commands gửi xuống STM32 (BẮT BUỘC CÓ \n ĐỂ STM32 NHẬN BIẾT KẾT THÚC) ──
CMD_UNLOCK_DOOR = "CMD_UNLOCK_DOOR"
CMD_LOCK_DOOR = "CMD_LOCK_DOOR"
CMD_ENABLE_KEYPAD = "CMD_ENABLE_KEYPAD"
CMD_WARNING_BEEP = "CMD_WARNING_BEEP"
CMD_STOP_ALARM = "CMD_STOP_ALARM"
CMD_TEST_BUZZER = "CMD_TEST_BUZZER"
CMD_SET_PIN = "CMD_SET_PIN"
# ── Responses/Events từ STM32 (PHẢI KHỚP 100% VỚI FILE app_main.c) ────────
EVT_MOTION_DETECTED = "EVENT_PIR_MOTION"
RSP_DOOR_OPENED = "DOOR_OPENED" # Tạm giữ nếu dùng cho nút Exit
RSP_DOOR_OPENED_PWD = "EVENT_DOOR_OPENED_PWD"
RSP_PASSWORD_FAILED = "EVENT_PWD_FAILED"
RSP_ALARM_ACTIVE = "ALARM_ACTIVE"
RSP_ACK_PIN_SET = "ACK_PIN_SET"

# ── Log rotation ──────────────────────────────────────────────────────────
LOG_MAX_BYTES = 5_000_000       # Giới hạn 5 MB mỗi file log
LOG_BACKUP_COUNT = 5            # Giữ lại 5 bản cũ → Tối đa chiếm ~30 MB trên SD card

# ── Camera ────────────────────────────────────────────────────────────────
CAMERA_WIDTH = 640              # Chiều rộng khung hình
CAMERA_HEIGHT = 480             # Chiều cao khung hình (VGA là tối ưu nhất cho Pi 4)
CAMERA_FPS = 15                 # Số khung hình/giây
CAMERA_WARMUP_SECONDS = 1.5     # Thời gian chờ cảm biến camera ổn định độ sáng (Auto Exposure)

# ── API ───────────────────────────────────────────────────────────────────
API_HEARTBEAT_INTERVAL = 30     # Giây giữa mỗi lần ping báo cáo "Online" về server
API_TIMEOUT = 10                # Đã đồng bộ lên 10 giây cho khớp với Backend
API_RETRY_ATTEMPTS = 3          # Số lần thử lại API khi rớt mạng

# ── Cloud upload ──────────────────────────────────────────────────────────
UPLOAD_MAX_SIZE_MB = 5          # Dung lượng tối đa mỗi file ảnh upload
UPLOAD_QUALITY = 85             # Chất lượng nén JPEG (0-100) để tiết kiệm băng thông

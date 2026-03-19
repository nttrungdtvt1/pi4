#!/bin/bash
# Script cài đặt tự động cho dự án Smart Door trên Raspberry Pi
# Khuyến nghị chạy bằng lệnh: bash deploy/install.sh (KHÔNG dùng sudo ở ngoài cùng)

echo "====================================================="
echo " BẮT ĐẦU CÀI ĐẶT MÔI TRƯỜNG CHO SMART DOOR"
echo "====================================================="

# Lấy đường dẫn tuyệt đối của thư mục gốc dự án
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../" && pwd)"
cd "$DIR"

# 1. Cập nhật hệ thống và cài đặt các thư viện lõi của Linux (C/C++)
echo "[1/5] Đang cập nhật hệ thống và cài đặt system dependencies..."
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev build-essential cmake pkg-config
sudo apt-get install -y libjpeg-dev libpng-dev libtiff-dev
sudo apt-get install -y libavcodec-dev libavformat-dev libswscale-dev libv4l-dev
sudo apt-get install -y libxvidcore-dev libx264-dev
sudo apt-get install -y libopenblas-dev liblapack-dev gfortran

# 2. Tạo môi trường ảo tên là 'door' theo đúng thiết kế
echo "[2/5] Đang tạo môi trường ảo Python (door)..."
python3 -m venv door

# 3. Cài đặt các thư viện Python từ requirements.txt
echo "[3/5] Đang cài đặt thư viện Python (Quá trình này có thể tốn 15-30 phút do build dlib)..."
source door/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Thiết lập Systemd Service để chạy ngầm
echo "[4/5] Đang thiết lập Systemd Service..."
# Sử dụng đường dẫn tuyệt đối $DIR để đảm bảo copy đúng file
sudo cp "$DIR/deploy/smart-door.service" /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/smart-door.service
sudo systemctl daemon-reload
sudo systemctl enable smart-door.service

# 5. Phân quyền cho các thư mục data
echo "[5/5] Đang cấp quyền cho thư mục dữ liệu (Sửa lỗi thư mục logging_module)..."
mkdir -p data/captures data/temp_uploads data/known_faces logging_module/logs
sudo chmod -R 775 data/
sudo chmod -R 775 logging_module/

echo "====================================================="
echo " CÀI ĐẶT HOÀN TẤT! 🎉"
echo " Vui lòng điền thông tin vào file .env, sau đó chạy lệnh:"
echo " sudo systemctl start smart-door.service"
echo " (Để xem log trực tiếp, dùng lệnh: journalctl -u smart-door.service -f)"
echo "====================================================="

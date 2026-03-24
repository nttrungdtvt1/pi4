# # recognition/enroll_face.py
# """
# CLI Tool để đăng ký khuôn mặt mới vào hệ thống.
# Cách dùng: python enroll_face.py --name "Nguyen Van A" --samples 5
# """
# from __future__ import annotations

# import argparse
# import asyncio
# import sys
# from pathlib import Path

# import cv2
# import aiohttp

# # Đảm bảo có thể chạy script này độc lập từ bất kỳ thư mục nào
# sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# from config.settings import settings
# from vision.camera_manager import CameraManager
# from vision.frame_processor import preprocess
# from recognition.face_encoder import encode_face, load_known_faces, save_known_faces


# async def enroll(name: str, resident_id: int | None = None, num_samples: int = 5) -> None:
#     print("=" * 50)
#     print(f" BẮT ĐẦU ĐĂNG KÝ KHUÔN MẶT: {name.upper()}")
#     print(f" Yêu cầu: {num_samples} mẫu ảnh. Vui lòng nhìn thẳng vào camera.")
#     print("=" * 50)

#     last_frame = None  # Biến giữ lại tấm ảnh cuối cùng
#     camera = CameraManager()
#     new_encodings = []

#     async with camera as cam:
#         print("\n[INFO] Đang khởi động camera...")
#         await asyncio.sleep(1.5)  # Chờ cảm biến cân bằng sáng (Warmup)

#         while len(new_encodings) < num_samples:
#             frame = await cam.capture_frame()
#             if frame is None:
#                 continue

#             last_frame = frame

#             processed = preprocess(frame)
#             if processed is None:
#                 continue

#             # Trích xuất đặc trưng khuôn mặt (128-d vector)
#             encodings = encode_face(processed)

#             if not encodings:
#                 # Dùng print với end='\r' để ghi đè dòng log trên Terminal, tránh trôi màn hình
#                 print("\r[-] Không tìm thấy khuôn mặt! Vui lòng đứng vào giữa khung hình.", end="")
#                 # BỎ SLEEP Ở ĐÂY để camera không bị kẹt buffer
#                 continue

#             if len(encodings) > 1:
#                 print("\n[-] Cảnh báo: Phát hiện nhiều khuôn mặt! Vui lòng chỉ đứng 1 mình.")
#                 await asyncio.sleep(1.0) # Có thể sleep ở đây vì đây là case ít gặp
#                 continue

#             # Xóa dòng cảnh báo (nếu có) và in kết quả thành công
#             print("\r" + " " * 80 + "\r", end="")
#             new_encodings.append(encodings[0])
#             print(f"[+] Đã chụp thành công mẫu {len(new_encodings)}/{num_samples}")

#             # Cố tình delay 0.5s giữa các lần chụp thành công để lấy các góc mặt hơi khác nhau một chút
#             await asyncio.sleep(0.5)

#     print("\n[INFO] Thu thập xong. Đang lưu dữ liệu vào hệ thống...")

#     # Tải dữ liệu cũ lên và cập nhật
#     known_faces = load_known_faces()
#     if name in known_faces:
#         print(f"[INFO] Tên '{name}' đã tồn tại. Đang ghi chú thêm mẫu nhận diện mới.")
#         known_faces[name].extend(new_encodings)
#     else:
#         known_faces[name] = new_encodings

#     # Lưu xuống file .pkl
#     if save_known_faces(known_faces):
#         print("\n" + "=" * 50)
#         print(f" HOÀN TẤT! Đã đăng ký thành công cho: {name}")
#         print("=" * 50)
#     else:
#         print("\n[ERROR] Có lỗi xảy ra khi lưu file known_faces.pkl")
#         return

#     # ========================================================
#     # ĐẨY ẢNH ĐẠI DIỆN LÊN DASHBOARD
#     # ========================================================
#     if resident_id is not None and last_frame is not None:
#         print("\n[INFO] Đang đẩy ảnh đại diện lên Web Dashboard...")
#         try:
#             # SỬA LỖI MÀU: opencv-python mặc định chụp RGB, nhưng imencode cần BGR
#             corrected_frame = cv2.cvtColor(last_frame, cv2.COLOR_RGB2BGR)

#             # Nén ảnh thành JPG trong RAM (không ghi ra thẻ nhớ)
#             _, buffer = cv2.imencode('.jpg', corrected_frame)
#             url = f"{settings.api_server_url}/api/residents/{resident_id}/face-image"

#             headers = {"Authorization": f"Bearer {settings.api_key}"}

#             # Khởi tạo FormData chuẩn của aiohttp
#             data = aiohttp.FormData()
#             data.add_field('file', buffer.tobytes(), filename='avatar.jpg', content_type='image/jpeg')

#             async with aiohttp.ClientSession() as session:
#                 async with session.post(url, data=data, headers=headers) as resp:
#                     if resp.status in (200, 201):
#                         print(f"[INFO] Upload ảnh thành công! (Mã: {resp.status})")
#                     else:
#                         error_text = await resp.text()
#                         print(f"[-] Lỗi upload: API trả về mã {resp.status} - {error_text}")

#         except Exception as e:
#             print(f"[-] Lỗi kết nối mạng khi upload ảnh: {e}")


# def main():
#     parser = argparse.ArgumentParser(description="Tool đăng ký khuôn mặt cho Smart Door")
#     parser.add_argument("--name", type=str, required=True, help="Tên người cần đăng ký")
#     parser.add_argument("--samples", type=int, default=5, help="Số lượng ảnh mẫu cần chụp")
#     args = parser.parse_args()

#     try:
#         # Chạy event loop cho script độc lập
#         asyncio.run(enroll(args.name, resident_id=None, num_samples=args.samples))
#     except KeyboardInterrupt:
#         print("\n\n[WARNING] Đã hủy quá trình đăng ký bởi người dùng (Ctrl+C).")

# if __name__ == "__main__":
#     main()



# # pi4/recognition/enroll_face.py
# """
# CLI Tool đăng ký khuôn mặt mới.

# Dùng: python enroll_face.py --name "Nguyen Van A" --samples 5 [--id 3]

# THIẾT KẾ:
#   - Chụp NUM_SAMPLES frame, lấy frame nào detect được mặt.
#   - Lưu vào known_faces.pkl ngay trên Pi.
#   - Nếu có --id: upload ảnh đại diện lên Web Dashboard.
#   - Không phụ thuộc face_recognition phức tạp — dùng encode_face() mới.
# """
# from __future__ import annotations

# import argparse
# import asyncio
# import sys
# from pathlib import Path

# import cv2
# import aiohttp

# sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# from config.settings import settings
# from vision.camera_manager import CameraManager
# from recognition.face_encoder import (
#     encode_face,
#     load_known_faces,
#     save_known_faces,
#     _ensure_dlib_compatible,
# )


# async def enroll(name: str, resident_id: int | None = None, num_samples: int = 5) -> None:
#     print("=" * 50)
#     print(f" ĐĂNG KÝ KHUÔN MẶT: {name.upper()}")
#     print(f" Cần {num_samples} mẫu. Nhìn thẳng vào camera.")
#     print("=" * 50)

#     new_encodings = []
#     last_frame = None
#     camera = CameraManager()

#     async with camera as cam:
#         print("\n[*] Khởi động camera...")
#         await asyncio.sleep(2.0)

#         fail_streak = 0

#         while len(new_encodings) < num_samples:
#             frame = await cam.capture_frame()
#             if frame is None:
#                 await asyncio.sleep(0.3)
#                 continue

#             last_frame = frame

#             # Đảm bảo dlib-compatible trước khi encode
#             img = _ensure_dlib_compatible(frame)
#             encodings = encode_face(img)

#             if not encodings:
#                 fail_streak += 1
#                 print(f"\r[-] Không thấy mặt... ({fail_streak})", end="", flush=True)
#                 if fail_streak >= 20:
#                     print("\n[!] Quá nhiều lần thất bại. Kiểm tra lại camera và ánh sáng.")
#                     return
#                 await asyncio.sleep(0.4)
#                 continue

#             if len(encodings) > 1:
#                 print("\n[!] Nhiều mặt trong khung — chỉ đứng 1 mình.")
#                 await asyncio.sleep(1.0)
#                 continue

#             fail_streak = 0
#             new_encodings.append(encodings[0])
#             print(f"\r[+] Mẫu {len(new_encodings)}/{num_samples} OK" + " " * 20)
#             await asyncio.sleep(0.5)

#     print(f"\n[*] Đã thu {len(new_encodings)} mẫu. Đang lưu...")

#     # Lưu vào known_faces.pkl
#     known = load_known_faces()
#     if name in known:
#         print(f"[*] '{name}' đã có. Thêm mẫu mới vào.")
#         known[name].extend(new_encodings)
#     else:
#         known[name] = new_encodings

#     if save_known_faces(known):
#         print(f"\n{'='*50}")
#         print(f" XONG! Đã đăng ký: {name}")
#         print(f"{'='*50}")
#     else:
#         print("\n[ERROR] Lưu pkl thất bại!")
#         return

#     # Upload ảnh đại diện lên Dashboard nếu có resident_id
#     if resident_id is not None and last_frame is not None:
#         print("\n[*] Upload ảnh đại diện lên Dashboard...")
#         try:
#             bgr = cv2.cvtColor(last_frame, cv2.COLOR_RGB2BGR)
#             _, buffer = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])

#             url = f"{settings.api_server_url}/api/residents/{resident_id}/face-image-from-pi"
#             headers = {"X-Pi-Api-Key": settings.api_key}

#             data = aiohttp.FormData()
#             data.add_field("file", buffer.tobytes(),
#                            filename="avatar.jpg", content_type="image/jpeg")

#             async with aiohttp.ClientSession() as session:
#                 async with session.post(url, data=data, headers=headers) as resp:
#                     if resp.status in (200, 201):
#                         print(f"[+] Upload OK (status {resp.status})")
#                     else:
#                         text = await resp.text()
#                         print(f"[-] Upload lỗi: {resp.status} — {text}")

#         except Exception as exc:
#             print(f"[-] Upload exception: {exc}")


# def main() -> None:
#     parser = argparse.ArgumentParser(description="Smart Door — Đăng ký khuôn mặt")
#     parser.add_argument("--name", type=str, required=True, help="Tên người đăng ký")
#     parser.add_argument("--samples", type=int, default=5, help="Số mẫu cần chụp")
#     parser.add_argument("--id", type=int, default=None, help="Resident ID trên Dashboard")
#     args = parser.parse_args()

#     try:
#         asyncio.run(enroll(args.name, resident_id=args.id, num_samples=args.samples))
#     except KeyboardInterrupt:
#         print("\n\n[!] Hủy bởi người dùng.")


# if __name__ == "__main__":
#     main()

# pi4/recognition/enroll_face.py
"""
CLI Tool đăng ký khuôn mặt mới.

Dùng: python enroll_face.py --name "Nguyen Van A" --samples 5 [--id 3]

THIẾT KẾ:
  - Chụp NUM_SAMPLES frame, lấy frame nào detect được mặt.
  - Lưu vào known_faces.pkl ngay trên Pi.
  - Nếu có --id: upload ảnh đại diện lên Web Dashboard.
  - Không phụ thuộc face_recognition phức tạp — dùng encode_face() mới.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import cv2
import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from vision.camera_manager import CameraManager
from recognition.face_encoder import (
    encode_face,
    load_known_faces,
    save_known_faces,
    _ensure_dlib_compatible,
)


async def enroll(name: str, resident_id: int | None = None, num_samples: int = 5) -> None:
    print("=" * 50)
    print(f" ĐĂNG KÝ KHUÔN MẶT: {name.upper()}")
    print(f" Cần {num_samples} mẫu. Nhìn thẳng vào camera.")
    print("=" * 50)

    new_encodings = []
    last_frame = None
    camera = CameraManager()

    async with camera as cam:
        print("\n[*] Khởi động camera...")
        await asyncio.sleep(2.0)

        fail_streak = 0

        while len(new_encodings) < num_samples:
            frame = await cam.capture_frame()
            if frame is None:
                await asyncio.sleep(0.3)
                continue

            last_frame = frame

            # Đảm bảo dlib-compatible trước khi encode
            img = _ensure_dlib_compatible(frame)
            encodings = encode_face(img)

            if not encodings:
                fail_streak += 1
                print(f"\r[-] Không thấy mặt... ({fail_streak})", end="", flush=True)
                if fail_streak >= 20:
                    print("\n[!] Quá nhiều lần thất bại. Kiểm tra lại camera và ánh sáng.")
                    return
                await asyncio.sleep(0.4)
                continue

            if len(encodings) > 1:
                print("\n[!] Nhiều mặt trong khung — chỉ đứng 1 mình.")
                await asyncio.sleep(1.0)
                continue

            fail_streak = 0
            new_encodings.append(encodings[0])
            print(f"\r[+] Mẫu {len(new_encodings)}/{num_samples} OK" + " " * 20)
            await asyncio.sleep(0.5)

    print(f"\n[*] Đã thu {len(new_encodings)} mẫu. Đang lưu...")

    # Lưu vào known_faces.pkl
    known = load_known_faces()
    if name in known:
        print(f"[*] '{name}' đã có. Thêm mẫu mới vào.")
        known[name].extend(new_encodings)
    else:
        known[name] = new_encodings

    if save_known_faces(known):
        print(f"\n{'='*50}")
        print(f" XONG! Đã đăng ký: {name}")
        print(f"{'='*50}")
    else:
        print("\n[ERROR] Lưu pkl thất bại!")
        return

    # Upload ảnh đại diện lên Dashboard nếu có resident_id
    if resident_id is not None and last_frame is not None:
        print("\n[*] Upload ảnh đại diện lên Dashboard...")
        try:
            bgr = cv2.cvtColor(last_frame, cv2.COLOR_RGB2BGR)
            _, buffer = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 90])

            url = f"{settings.api_server_url}/api/residents/{resident_id}/face-image-from-pi"
            headers = {"X-Pi-Api-Key": settings.api_key}

            data = aiohttp.FormData()
            data.add_field("file", buffer.tobytes(),
                           filename="avatar.jpg", content_type="image/jpeg")

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers) as resp:
                    if resp.status in (200, 201):
                        print(f"[+] Upload OK (status {resp.status})")
                    else:
                        text = await resp.text()
                        print(f"[-] Upload lỗi: {resp.status} — {text}")

        except Exception as exc:
            print(f"[-] Upload exception: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Door — Đăng ký khuôn mặt")
    parser.add_argument("--name", type=str, required=True, help="Tên người đăng ký")
    parser.add_argument("--samples", type=int, default=5, help="Số mẫu cần chụp")
    parser.add_argument("--id", type=int, default=None, help="Resident ID trên Dashboard")
    args = parser.parse_args()

    try:
        asyncio.run(enroll(args.name, resident_id=args.id, num_samples=args.samples))
    except KeyboardInterrupt:
        print("\n\n[!] Hủy bởi người dùng.")


if __name__ == "__main__":
    main()

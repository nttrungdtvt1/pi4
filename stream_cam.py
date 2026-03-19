import cv2
from flask import Flask, Response

app = Flask(__name__)
# Dùng backend opencv cho camera USB
camera = cv2.VideoCapture(0)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            # Nén frame thành chuẩn JPEG để đẩy lên web
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            
            # Yield dữ liệu liên tục để tạo luồng video
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def video_feed():
    # Trả về video stream
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 MÁY CHỦ CAMERA ĐÃ CHẠY!")
    print("👉 Mở trình duyệt web của bạn và truy cập vào địa chỉ:")
    print("   http://<Địa_chỉ_IP_của_Raspberry_Pi>:5000")
    print("   (Ví dụ: http://192.168.1.x:5000)")
    print("Ấn Ctrl+C để tắt luồng video khi đã căn chỉnh xong.")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=False)

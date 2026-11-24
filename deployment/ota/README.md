# Khóa công khai xác minh chữ ký Firmware OTA

Thư mục này là nơi đặt tệp `public.pem` chứa **khóa công khai RSA-2048** dùng để Backend xác minh chữ ký số của các gói manifest cập nhật firmware.

- Tạo cặp khóa bằng công cụ `backend/scripts/ota_firmware.py init-key`: khóa công khai đặt tại `deployment/ota/public.pem` (được mount ở chế độ chỉ đọc `read-only` vào container Backend), còn **khóa bí mật (private key)** lưu tại thư mục bảo mật riêng ngoài Git.
- Xem hướng dẫn đầy đủ tại [docs/firmware-ota.md](../../docs/firmware-ota.md).

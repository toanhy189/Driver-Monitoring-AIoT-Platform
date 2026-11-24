# Chỉ mục kiểm thử hệ thống

Thư mục này tập hợp kịch bản nghiệm thu đầu-cuối và dẫn chiếu trực tiếp tới mã kiểm thử của cả 4 thành phần trong hệ thống (đồng bộ với pipeline CI tại [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).

---

## 1. Kịch bản nghiệm thu & kiểm thử hệ thống

- **[Kịch bản kiểm thử tích hợp và nghiệm thu 10 bước](final-acceptance.md):** Danh sách chuẩn bị demo, quy trình nghiệm thu chức năng 10 bước và phương pháp đo các chỉ tiêu phi chức năng.

---

## 2. Mã kiểm thử theo từng thành phần

| Thành phần | Thư mục mã kiểm thử | Phạm vi kiểm thử | Lệnh chạy chuẩn (theo CI) |
|---|---|---|---|
| **Backend (Unit & Contract)** | [`backend/tests/`](../backend/tests/) | Xác thực JWT, phân quyền RBAC 3 vai trò, hợp đồng API, chính sách AI, ràng buộc lệnh/cảnh báo, tài khoản MQTT và xử lý video | `python -m unittest discover -s backend/tests -v` |
| **Backend (Tích hợp Docker)** | [`backend/tests/run_week4_isolated.py`](../backend/tests/run_week4_isolated.py)<br>[`backend/tests/run_rule_binding_postgres.py`](../backend/tests/run_rule_binding_postgres.py) | Kiểm thử tích hợp với PostgreSQL 16 & Mosquitto 2 thật: phân quyền/ACL, đồng thời rule-binding/ACK, vòng đời OTA có ký số và khởi động lại bền vững | `python backend/tests/run_week4_isolated.py --regression`<br>`python backend/tests/run_rule_binding_postgres.py`<br>`python backend/tests/run_rule_binding_postgres.py --suite test_ota_postgres.py` |
| **Edge AI (Runtime & ML v2)** | [`edge-ai/tests/`](../edge-ai/tests/) | Kiểm tra môi trường nạp mô hình (`--check`), chỉ số EAR/MAR/PERCLOS, hiệu chuẩn mắt đeo kính, tư thế đầu 3D, hợp nhất đa tín hiệu v2, hàng đợi ngoại tuyến SQLite và khôi phục kết nối | `python edge-ai/main.py --check`<br>`python -m unittest discover -s edge-ai/tests -v` |
| **Frontend (Unit & Build)** | [`frontend/tests/`](../frontend/tests/) | Phân quyền giao diện, điều hướng, chuỗi dữ liệu biểu đồ, quản lý thiết bị/lệnh/cảnh báo/luật, tương thích WebSocket và build sản phẩm Vite *(kèm các kịch bản kiểm thử trình duyệt `*.cjs`)* | `node --test frontend/tests/*.test.mjs`<br>`npm --prefix frontend run build` |
| **Firmware ESP32 (Build & Hardware Test)** | [`firmware/esp32-alert-node/src/tests/main.cpp`](../firmware/esp32-alert-node/src/tests/main.cpp) | Kiểm tra biên dịch firmware cho hai cấu hình `development` & `ota-release` (tự động dùng `ota_trust.example.h` khi không có khóa cục bộ) và mã kiểm thử phần cứng trên mạch ESP32 | `python -m platformio run -d firmware/esp32-alert-node -e development`<br>`python -m platformio run -d firmware/esp32-alert-node -e ota-release` |

---

## 3. Lưu ý môi trường khi chạy kiểm thử cục bộ

- **Backend unit test:** Cần đặt biến môi trường `DATABASE_URL=postgresql+psycopg://test:test@localhost/test` và `SECRET_KEY=ci-only-no-deployment-access` (giống `.github/workflows/ci.yml`); các ca yêu cầu PostgreSQL/Mosquitto sống sẽ tự bỏ qua (`SKIP`) khi chạy `unittest discover` độc lập và được thực thi đầy đủ qua 3 lệnh tích hợp Docker ở bảng trên.
- **Edge AI:** Để kiểm thử nạp mô hình từ gói phát hành (Release Assets), giải nén gói `multisignal-v2-*.zip`, kiểm tra mã băm `.sha256`, rồi truyền thư mục chứa `manifest.json` qua `-BundlePath` của `edge-ai/run-multisignal-v2.ps1`. Ví dụ: `./edge-ai/run-multisignal-v2.ps1 -Demo -Condition no-glasses -BundlePath './edge-ai/models/multisignal-v2-20261110' -Check`. Lệnh này chỉ kiểm tra nạp, không mở camera; khi chạy camera thật phải chọn đúng điều kiện kính và profile tương ứng. Xem [`README.md`](../README.md) và [`edge-ai/README.md`](../edge-ai/README.md).

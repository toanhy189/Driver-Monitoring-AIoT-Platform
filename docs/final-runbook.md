# Chạy, kiểm tra và bàn giao bản cuối

## 1. Chuẩn bị

Windows + Docker Desktop, Python 3.13 cho Edge AI, Node 22 nếu chạy FE native, PlatformIO cho ESP32. Giữ `.env`, Wi-Fi/credential board và model ngoài Git. Không dùng `database/create.sql` cho DB đang có dữ liệu vì file này khởi tạo lại schema.

Với DB hiện có: sao lưu trước khi nâng cấp. Bản ngày 08/11/2026 đã được sao lưu vào `.local-backups/final-completion-20261108/`; đã thử restore vào DB tạm riêng, không ghi đè DB thật. Backup chứa dữ liệu riêng, không đưa vào bài nộp/GitHub.

Với máy mới: copy `.env.example` thành `.env`; thay thông tin DB, SECRET_KEY, địa chỉ; chuẩn bị credential:

```powershell
python deployment/mqtt/prepare_env.py
python deployment/prepare_final_env.py
```

Hai script chỉ bổ sung giá trị thiếu, không in secret. `database/insert.sql` là dữ liệu mẫu đang được Compose nạp khi volume PostgreSQL trống; tài khoản/node/số đo mẫu không chứng minh thiết bị thật hoạt động. Không nạp lại insert vào DB nhóm đang dùng. Trước vận hành thật phải thay credential mẫu và kiểm tra người dùng/quyền; không công bố dịch vụ này ra Internet bằng cấu hình demo.

## 2. Docker

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml up -d --build backend frontend time-server
docker compose --env-file .env -f deployment/docker-compose.yml ps
```

Địa chỉ: React `http://localhost:5173`, Swagger `http://localhost:8000/docs`; MQTT từ máy native dùng cổng **1884**, container dùng `mosquitto:1883`. Dùng `up -d` khi code không thay đổi; `--build` dùng cache, không mặc định tải lại mọi thứ. Không chạy `down -v` vì sẽ xóa volume dữ liệu.

Migration dùng `ALTER ... IF NOT EXISTS`, bảo toàn dữ liệu. Nếu báo unique index do username/assignment trùng, dừng và xem bản ghi; không tự xóa để bỏ qua lỗi.

## 3. Monitoring phụ trợ

### HTTPS tùy chọn đã có

```powershell
python deployment/tls/prepare_certs.py
docker compose --env-file .env -f deployment/docker-compose.yml -f deployment/docker-compose.tls.yml up -d --no-deps frontend
```

React/API/WSS đi qua `https://localhost:8443`. CA và private key nằm trong `deployment/tls/certs/`, ngoài Git và Docker build context. Script không cài CA vào Windows. Browser sẽ chưa tin CA riêng nếu chưa cấu hình trust; không coi việc bỏ qua cảnh báo chứng chỉ là nghiệm thu xác thực TLS. Có thể kiểm tra bằng client chỉ định đúng file CA. Nếu muốn truy cập bằng IP LAN, tạo certificate với `--host <IP-laptop>` ngay từ đầu; script giữ nguyên bộ chứng chỉ đã tồn tại.

Edge upload có thể dùng cổng HTTPS này bằng cách đặt trước khi chạy AI:

```powershell
$env:BACKEND_HOST = "https://localhost:8443"
$env:REQUESTS_CA_BUNDLE = (Resolve-Path deployment/tls/certs/ca.crt).Path
```

Giữ xác minh CA; không dùng `verify=False`. MQTT của bản demo vẫn là plain MQTT trong LAN; Backend sau Nginx dùng mạng Docker nội bộ. HTTPS này không đồng nghĩa mọi đường truyền đã mã hóa. Nếu dùng nhiều overlay, giữ cả ba `-f` base/TLS/monitoring trong các lệnh triển khai để tránh gỡ cấu hình overlay khác.

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml -f deployment/docker-compose.monitoring.yml up -d prometheus grafana
```

Prometheus: `http://127.0.0.1:9090`; Grafana: `http://127.0.0.1:3000`, user `admin`, password đọc từ `.env` riêng. `/metrics` của BE đòi `METRICS_TOKEN`, JWT người dùng không thay được secret này. Không copy token vào slide.

Exporter AI, chạy ở terminal riêng từ `edge-ai` sau khi chuẩn bị môi trường:

```powershell
cd edge-ai
./.venv/Scripts/python.exe -X utf8 -m service.metrics_server --host 0.0.0.0 --port 9108
```

Camera chưa chạy hoặc số đo quá 30 giây: exporter trả 503, Prometheus hiển thị down/no data. Không điền số FPS/latency giả. `0.0.0.0` để Docker Desktop truy cập host; chỉ dùng LAN thử. Không tự tạo firewall rule.

## 4. AI

```powershell
python -m venv edge-ai/.venv
./edge-ai/.venv/Scripts/python.exe -m pip install -r edge-ai/requirements-lock.txt
./edge-ai/run-submission.ps1 -Check
./edge-ai/run-submission.ps1
```

Copy model riêng đúng đường dẫn/hash trước lệnh cuối; xem [model card](final-ai-model.md). Nhìn thẳng để hiệu chuẩn, dùng ánh sáng phù hợp. Clip/queue ở đường dẫn cấu hình Edge; video đã upload ở Docker volume `deployment_video_data`, không phải thư mục public của React.

Mở Camera là bắt đầu ghi clip theo chương trình. Nếu dùng gương mặt người khác, xin đồng ý trước. Backend giữ clip cho tới khi người có quyền xóa; quota đầy trả 507, Edge giữ clip để retry.

## 5. ESP32 và giờ LAN

Build đã kiểm tra bằng:

```powershell
pio run -d firmware/esp32-alert-node -e development
python deployment/time/check_ntp.py
```

Đã thấy USB-SERIAL CH340 COM4; người dùng xác nhận là ESP32 nhưng **mạch chưa kiểm tra**, chỉ chuẩn bị firmware. Chưa flash hoặc phát lệnh tải. TV1 hoàn tất [xác nhận phần cứng](../hardware/README.md) trước bước nạp.

File `include/network_config.h` riêng có Wi-Fi nhưng MQTT_USER/MQTT_PASSWORD còn trống ở lần kiểm tra. Dùng credential cấp cho đúng `alert-01`, MQTT_HOST là IP LAN của laptop, cổng **1884** với Compose hiện tại. Không dùng credential Backend/admin cho board. Nếu node đã provisioned thì phối hợp TV2 lấy đúng credential; không tự cấp lại làm mất kết nối của người đang dùng.

Firmware hỏi NTP tại MQTT_HOST trước, rồi nguồn Internet dự phòng. chrony dùng giờ laptop làm tham chiếu; kiểm tra đúng ngày/giờ laptop. Probe localhost đạt chỉ chứng minh dịch vụ NTP trên máy, không chứng minh ESP32 đã đồng bộ qua Wi-Fi. Nếu LAN bị Windows Firewall chặn UDP 123, ghi rõ interface/profile/IP thiết bị và xin duyệt rule cụ thể trước khi sửa.

## 6. Bật policy cho nghiệm thu

Giữ phiên bản `driver-bench-20261107-v1`. TV2 kiểm tra `RULE_ENGINE_ENABLED`, binding camera→đúng ESP32, ACTIVE/ONLINE và clock board. Không sửa ngưỡng để demo. Chạy [kịch bản nghiệm thu](../tests/final-acceptance.md), ghi event_id, request_id và kết quả tải quan sát được.

## 7. Kiểm thử và CI

```powershell
python -X utf8 -m unittest discover -s backend/tests -v
python -X utf8 backend/tests/run_week4_isolated.py --regression
python -X utf8 backend/tests/run_week4_isolated.py --restart-only
./edge-ai/.venv/Scripts/python.exe -X utf8 -m unittest discover -s edge-ai/tests -v
node --test frontend/tests/*.test.mjs
npm --prefix frontend run build
```

Runner tích hợp tạo DB/broker tạm; không thay DB ứng dụng và không dùng tải vật lý. Giữ output ngày cũ, chỉ ghi kết quả mới vào thư mục mới. CI chạy tự động kiểm thử và build; không tự deploy vào laptop bằng credential GitHub. Giai đoạn CD trong bản này thực hiện bằng lệnh Compose sau kiểm tra, không tuyên bố tự động deploy khi workflow chưa làm việc đó.

Kiểm thử browser tùy chọn: `frontend/tests/final-browser-smoke.cjs`, Playwright cài ngoài repo, Edge có sẵn, chỉ dùng Customer QA tạm. Không cần tạo Admin thêm để chạy ca này.

## 8. Bàn giao và release

- Git: source, migration, template, tài liệu, kết quả tổng hợp đã xem lại; mỗi TV dùng tài khoản Git của mình.
- Riêng tư: model bundle/hash, `.env`, credential board, backup DB và video minh chứng được phép chia sẻ.
- Trước tag bản cuối: tất cả ca vật lý còn trống phải có kết quả, nhóm xem lại số liệu/slide/báo cáo, chạy rehearsal và clip dự phòng. Không gắn nhãn “đã hoàn thành toàn bộ” khi chưa nghiệm thu phần cứng.

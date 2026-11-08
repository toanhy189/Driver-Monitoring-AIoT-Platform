# Backend — FastAPI

Backend phục vụ REST API, WebSocket, MQTT consumer, Rule Engine và PostgreSQL. Consumer MQTT chạy trong vòng đời FastAPI; không chạy thêm consumer riêng.

## Chạy

Cách chính: [README dự án](../README.md), dùng Compose ở `deployment/docker-compose.yml`.

Nếu phát triển Backend trực tiếp, chuẩn bị PostgreSQL/broker/migration bằng Compose, dừng service Backend Docker để tránh trùng cổng, rồi dùng môi trường Python riêng:

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-test.txt
./backend/.venv/Scripts/python.exe -m uvicorn --app-dir backend app.main:app --reload
```

`DATABASE_URL` dùng localhost:5432, `MQTT_HOST=localhost`, `MQTT_PORT=1884`. Không dùng Python trong `edge-ai/.venv` để chạy Uvicorn. Swagger: <http://localhost:8000/docs>.

## API chính

| Chức năng | API |
|---|---|
| Phiên đăng nhập | `POST /api/login`, `POST /api/logout`, `GET /api/me` |
| Tài khoản | `POST /api/register`, `PUT /api/me`, `POST /api/me/password` |
| Admin quản lý tài khoản/gán thiết bị | `GET/POST /api/users`, `PATCH /api/users/{id}`, `PUT/DELETE /api/users/{id}/devices/{device_id}` |
| Thiết bị | `GET/POST /api/devices`, `GET /api/devices/{id}` |
| Vòng đời | `POST /api/devices/{id}/{provision,activate,maintenance,decommission}` |
| Telemetry | `GET /api/{id}/telemetry`, `GET /api/{id}/telemetry/history` |
| Lịch sử | `GET /api/devices/{id}/{history,timeline,metrics}` |
| Lệnh | `POST /api/devices/{id}/commands`, `GET /api/commands`, `GET /api/commands/{request_id}` |
| Cấu hình | `GET/PUT /api/devices/{id}/config` |
| Cảnh báo | `GET /api/alerts`, `POST /api/alerts/{id}/acknowledge` |
| Binding | `GET/PUT /api/devices/{id}/rule` |
| Realtime | `POST /api/ws-ticket`, `WS /ws/telemetry?ticket=...` |

Admin quản lý toàn hệ thống; Employee/Customer bị giới hạn bằng assignment và vai trò. Đăng ký công khai chỉ tạo Customer. Đổi mật khẩu/đăng xuất/khóa tài khoản thu hồi phiên JWT; ticket WebSocket có hạn và dùng một lần.

## Dữ liệu và thiết bị

- MQTT AI dùng `driver/{device_code}/{telemetry,events,status}`; BE lưu bản tin/receipt trước khi trả `storage_ack: SAVED`.
- Rule v1 cần cả cờ `RULE_ENGINE_ENABLED`, binding bật, đúng node, ACTIVE/ONLINE và event còn hạn. `STATE_CHANGED` không tự thay thế event đề nghị cảnh báo.
- `TEST_ALERT` chỉ hoàn tất khi ba lệnh con đủ ACK COMPLETED.
- Config lưu desired trước, applied sau ACK hợp lệ; firmware có revision và NVS.
- Video upload dùng HTTP Basic của Vision Node; xem/xóa dùng quyền người dùng. Backend chỉ xóa thủ công, kiểm tra quota và giữ tombstone khi đã xóa.
- Migration đang chạy được khai báo tại [Compose](../deployment/docker-compose.yml). Không chạy lại create/seed lên DB có dữ liệu.

Kiểm tra readiness chỉ đọc: `python backend/scripts/setup_ai_ingest.py`. Tùy chọn `--apply --assign-user TEN_ADMIN` là tác vụ thay đổi migration/ACL/đăng ký Vision Node; chỉ dùng khi hiểu trạng thái node, không dùng để bỏ qua vòng đời hay credential đã cấp.

## Kiểm thử

```powershell
python -m pip install -r backend/requirements-test.txt
python -X utf8 -m unittest discover -s backend/tests -v
python -X utf8 backend/tests/run_week4_isolated.py --regression
python -X utf8 backend/tests/run_week4_isolated.py --restart-only
```

Các runner tích hợp tạo DB/broker tạm riêng. Test không chứng minh LED/còi/motor đã chạy trên board thật.

Tham khảo: [hợp đồng AI/video](../docs/ai-ingest-video-contract.md), [kiến trúc/bảo mật](../docs/final-architecture-security.md), [kịch bản demo](../tests/final-acceptance.md).

# Báo cáo kết quả thực hiện Backend tuần 3 — TV2

**Cập nhật:** 19/10/2026, múi giờ Asia/Bangkok. **Phạm vi:** TV2-05 đến TV2-23 theo ảnh nhiệm vụ. **Nhánh bàn giao:** `feature/backend-week3`, đã đồng bộ các thay đổi FE/firmware của main đến `5e06f10`.

**Lần chạy tích hợp kết thúc:** 19/10/2026 16:14:54 (UTC+07:00).

**Kết luận:** phần code BE và các ca kiểm tra bên dưới đạt. Chưa thể đánh dấu hoàn thành toàn bộ tuần 3 vì còn chốt chính sách AI, hợp đồng với TV1/TV4 và kiểm tra phần cứng. Bảng nhiệm vụ ở mục 2 ghi rõ từng giới hạn; mục 7 dành cho người tiếp nhận BE tuần sau.

Code đã được bổ sung và kiểm tra với PostgreSQL thật, broker MQTT Docker thật, HTTP/WebSocket và một container BE riêng được restart trong bài test. ESP32 trong test là chương trình giả lập MQTT; không có bằng chứng còi/đèn/motor thật hoặc camera AI thật đã chạy toàn luồng.

Nhóm xác nhận **chưa chốt severity, cooldown và bảng W3**. Chính sách mẫu đã có code nhưng `RULE_ENGINE_ENABLED` mặc định `false`. Các giá trị mẫu và cách gán mã ca test trong tài liệu chưa được coi là thống nhất chính thức của TV1/TV3/TV4.

Tài liệu giải thích logic, hợp đồng JSON và cách chạy: [Hướng xử lý và logic code](TV2-tuan-3-huong-xu-ly-va-logic-code.md).

## 1. Kết quả kiểm tra có minh chứng

| Kiểm tra | Kết quả đã ghi nhận | Minh chứng gốc |
| --- | --- | --- |
| Test BE thông thường | 46 test được phát hiện; **29 chạy đạt**, 17 bỏ qua có chủ đích vì cần chế độ live riêng | [unit-output.txt](evidence/week3/unit-output.txt) |
| Tích hợp tuần 3 | **16/16 đạt; 0 lỗi; 0 bỏ qua**, có Docker restart | [integration-output.txt](evidence/week3/integration-output.txt), [integration-results.json](evidence/week3/integration-results.json) |
| ACL trên broker thật | **1/1 đạt**, gồm quyền đọc/gửi, gửi chéo, cấu hình retained và thu hồi tài khoản | [acl-output.txt](evidence/week3/acl-output.txt), [acl-results.json](evidence/week3/acl-results.json) |
| Test FE | **58/58 đạt** | [frontend-tests-output.txt](evidence/week3/frontend-tests-output.txt) |
| Build FE | Thành công | [frontend-build-output.txt](evidence/week3/frontend-build-output.txt) |
| Build firmware | PlatformIO môi trường **development SUCCESS** | [firmware-build-output.txt](evidence/week3/firmware-build-output.txt) |
| Migration DB đang cấu hình | Đã áp dụng migration bổ sung tuần 3; xác nhận hai bảng mới | [migration-results.json](evidence/week3/migration-results.json) |
| Migration chạy lại | Được chạy hai lần trên DB thử trước test, không lỗi | [run_week3_integration.py](../backend/tests/run_week3_integration.py), kết quả tích hợp ở trên |
| Cấu hình Compose | Kiểm tra `config -q` đạt, không in mật khẩu | [compose-results.json](evidence/week3/compose-results.json) |
| Dọn tài nguyên thử | Còn 0 database thử và 0 container thử; Rule Engine trên máy đang tắt | [resource-cleanup.json](evidence/week3/resource-cleanup.json) |

Các test live tạo database riêng tên `codex_w3_...`, tài khoản MQTT thử và container BE riêng, rồi tự dọn tài nguyên thử. DB ứng dụng không bị khởi tạo lại. Migration trên DB ứng dụng chỉ thêm bảng/cột/chỉ mục.

## 2. Kết quả theo từng đầu việc

| Mã | Phần đã thực hiện và kiểm chứng | Trạng thái và giới hạn |
| --- | --- | --- |
| **TV2-05** | Broker chặn thiết bị đọc lệnh/config hoặc gửi ACK/applied của thiết bị khác; AI không được giả làm ESP32 | **Đạt phía broker**. Test ACL thật có kết quả PASS. |
| **TV2-06** | Provision tạo tài khoản thật, trả mật khẩu một lần; decommission thu hồi kết nối và chặn HTTP command/config | **Đạt phía BE/broker**. Test 01: provision 200, kết nối bị ngắt, login cũ bị từ chối, thao tác sau thu hồi trả 409. |
| **TV2-07** | PUT lưu desired, config_id và revision; gửi config/update QoS 1 retained; giới hạn bật/tắt khớp firmware TV1 mới; hai PUT đầu đồng thời không tạo trùng dòng | **Code và test đạt; chờ TV1 xác nhận hợp đồng cuối**. Test 02/15 và kiểm tra publisher. |
| **TV2-08** | Publish lỗi trả 503, ghi PUBLISH_FAILED, không tự ghi applied; FE hiển thị lỗi và cho gửi lại | **Đạt phía BE/FE**. Test 03 xác nhận applied vẫn rỗng. |
| **TV2-09** | Kiểm tra đồng thời thiết bị, topic, config_id và status APPLIED; bỏ ACK sai/cũ/trùng; REJECTED lưu lý do | **Đạt phía BE**. Test 02 và test hợp đồng kiểm tra các trường hợp này. |
| **TV2-10** | Config offline nhận lại từ retained; body sai trả 422; ACK muộn/cũ không ghi đè desired/applied mới | **Một phần**: BE giả lập đạt, firmware TV1 build đạt. Firmware hiện chưa dùng revision để chặn config cũ đến lại và chưa so sánh nội dung khi trùng ID; cần TV1 xử lý/test board thật. |
| **TV2-11** | TEST_ALERT cha chỉ COMPLETED khi đủ ba ACK con COMPLETED | **Đạt trên MQTT với ESP32 giả lập**. Chưa có minh chứng tải vật lý thật. |
| **TV2-12** | ACK trùng/sai thiết bị không làm sai kết quả; ACK tới trước HTTP không bị ghi đè; thiếu ACK thành TIMEOUT; đủ ba ACK muộn mới giải quyết timeout; INTERRUPTED/REBOOTED thành thất bại | **Đạt phía BE**, test 04/05/11/16. |
| **TV2-13** | Restart container BE, đọc lại command/ACK/config/alert/event/history từ PostgreSQL; idempotency key vẫn hoạt động | **Đạt trong Docker thử**, test 12. |
| **TV2-14** | Chính sách mức 1–3/cooldown cấu hình được, kiểm tra ngưỡng tăng dần, có công tắc bật/tắt; mặc định tắt tự gửi | **Một phần**: nhóm chưa chốt thông số. Test 06/11 kiểm tra logic bằng giá trị mẫu. |
| **TV2-15** | Rule Engine tiếp nhận event, tạo alert/lệnh và lưu chuỗi event_id → alert_id → request_id trong một giao dịch; worker gửi lệnh đã lưu | **Đạt phía BE và MQTT giả lập**, test 06/13. Tích hợp AI/ESP32 thật vẫn cần nhóm. |
| **TV2-16** | Unique event_id trong PostgreSQL, khóa giao dịch; phát lại đồng thời hoặc từ process mới không tạo thêm alert/lệnh | **Đạt phía BE**, test 07. |
| **TV2-17** | Idempotency-Key theo user/device/body; trùng body lấy lệnh cũ; khác body trả 409; FE giữ khóa khi mất phản hồi; không tự retry POST | **Đạt với client có gửi khóa**, test 08/12/14 và test FE. Header tùy chọn để giữ tương thích client cũ. |
| **TV2-18** | Đã viết và triển khai hợp đồng history/telemetry/timeline/metrics: route, JSON, quyền, UTC, model_version, khoảng thời gian và phân trang | **Một phần về phối hợp**: hợp đồng trong code đã kiểm thử, còn TV4 xác nhận chính thức. |
| **TV2-19** | API mới lọc đúng thiết bị và model_version; schema vào OpenAPI; FE có lịch sử/thống kê; giữ API riêng cho biểu đồ mới của TV4, không trùng handler | **Đạt code/test BE–FE**, test 09 gồm kiểm tra UTC/quyền cho API biểu đồ; test FE và build. |
| **TV2-20** | Tách HTTP, MQTT publish, ACK và tổng thời gian hoàn tất bằng timestamp/đồng hồ BE; dữ liệu lưu DB và có metrics | **Đạt chức năng đo**, test 04. Số đo hiện tại dùng thiết bị giả lập, chưa phải đánh giá hiệu năng phần cứng. |
| **TV2-21** | Vé WS một lần/hết hạn; kiểm tra lại quyền gán đang mở; đổi role có hiệu lực với HTTP; restart Docker rồi xin vé/kết nối lại; ghi giới hạn RAM/multi-worker | **Đạt ca kiểm chứng**, test 10/12. Cấu hình vận hành hiện dùng một worker. |
| **TV2-22** | Chuẩn bị bảng W3-01…08, W3-10…13 đề xuất; các ca BE tương ứng được chạy và lưu output | **Một phần**: chưa có bảng W3 chính thức và chưa kiểm thử chung với phần cứng TV1/TV3. |
| **TV2-23** | Có migration, OpenAPI, hợp đồng API/WS, ACL mẫu, test thật phía BE/broker, mô tả Rule Engine và idempotency | **Đã chuẩn bị bộ bàn giao**; còn nhóm nghiệm thu thông số/hợp đồng và tích hợp phần cứng. |

“Đạt phía BE/broker” chỉ xác nhận phạm vi được nêu trong cột minh chứng; không thay cho việc nhìn thấy tải vật lý hoạt động trên board.

## 3. Một số minh chứng cụ thể

### 3.1. Config không được báo áp dụng sớm

Test 02 gửi PUT khi thiết bị chưa đăng ký nhận topic cấu hình. GET cho thấy applied rỗng. Thiết bị giả lập đăng ký sau vẫn nhận tin retained. Body thiếu timings trả 422. ACK sai ID/sai thiết bị bị bỏ qua; REJECTED giữ applied cũ; ACK APPLIED phù hợp mới cập nhật applied. Sau PUT thứ hai, revision bằng 2 và ACK cũ không thay thế cấu hình mong muốn mới.

Test 03 ép publisher thất bại, ghi được HTTP 503, `PUBLISH_FAILED`, `applied=null`. Đây là kiểm tra nhánh lỗi có chủ đích; các test MQTT khác dùng broker thật để kiểm tra nhánh gửi thành công.

### 3.2. Ba ACK con và số đo thời gian

Test 04 gửi ba lệnh qua broker thật và nhận ACK do chương trình ESP32 giả lập phát. Sau hai ACK, ack_status là ACCEPTED; sau ba ACK, ack_status là COMPLETED. Các số đo lấy từ BE, không lấy đồng hồ của ESP32.

Một mẫu ở lần chạy được lưu trong JSON:

| Số đo | Giá trị mẫu |
| --- | --- |
| HTTP phía BE | 351.729 ms |
| Tổng tới khi đủ COMPLETED | 490.144 ms |
| MQTT publish của LED | 25.684 ms |
| Bắt đầu publish tới ACK LED | 314.561 ms |

Đây là minh chứng cơ chế đo đang hoạt động. Không dùng các giá trị của thiết bị giả lập này để kết luận độ trễ thực tế của còi/rung trên ESP32.

### 3.3. Rule Engine đi hết luồng qua MQTT

Test 13 gửi sự kiện bằng tài khoản AI tới topic đang dùng `driver/events`; BE lưu quyết định và lệnh; worker phát ba lệnh; ESP32 giả lập gửi đủ ACK. Mẫu chuỗi liên kết: event `event-c8656100be00d805` → alert `11` → request `cmd-11`, mức 2/MEDIUM, ACK cuối COMPLETED. Gửi lại event không phát thêm lệnh.

Test 07 gửi đồng thời cùng event rồi phát lại từ một process Python mới, kết quả vẫn chỉ có một event, một alert và một lệnh cha. Test 14 giả lập BE dừng sau khi đã ghi dấu PUBLISHING, xác nhận session mới không gửi lại mù và cuối cùng ghi TIMEOUT với thông tin kết quả gửi chưa xác định.

Các event mức 2/3 trong test mang thời lượng giả lập tương ứng. AI thực tế hiện theo hướng gửi một event khi đạt 3 giây; chưa thể kết luận tăng mức theo thời gian đã chạy trọn luồng. Cooldown hiện chặn cả event mức cao hơn trong khoảng chờ. Đây là hai điểm cần thống nhất trước khi bật Rule Engine.

### 3.4. Restart Docker và WebSocket

Test 12 mở WebSocket thật tới container BE riêng bằng hai tài khoản. Tài khoản được gán nguồn nhận device.updated; tài khoản không được gán không nhận. Sau khi thu hồi gán thiết bị trong PostgreSQL, socket đang mở ngừng nhận dữ liệu nguồn. Vé dùng lại/hết hạn bị từ chối. Sau restart container, xin vé mới để kết nối lại và nhận trạng thái thiết bị.

Sau restart, API vẫn trả lệnh COMPLETED, config đã applied, lịch sử, alert và timeline event. POST cùng idempotency key vẫn trả request_id cũ. Log container được che giá trị ticket: [docker-be-output.txt](evidence/week3/docker-be-output.txt).

### 3.5. Đồng thời và ACK reboot theo firmware mới

Test 15 gửi đồng thời hai PUT cấu hình đầu tiên: cả hai HTTP 200, DB chỉ có một dòng cấu hình, revision cuối bằng 2; tin retained khớp config_id desired cuối. Test 16 gửi `INTERRUPTED` với lỗi `REBOOTED` qua broker thật: lệnh cha chuyển FAILED, giữ lỗi REBOOTED và không báo COMPLETED. Hai ca này được ghi trong integration-results.json.

## 4. Các thay đổi code chính

| Nhóm code | File tiêu biểu |
| --- | --- |
| Schema/migration tuần 3 | [migration_be_week3.sql](../database/migration_be_week3.sql), [ai_event.py](../backend/app/models/ai_event.py), các trường command/config/telemetry |
| Rule Engine | [rule_engine.py](../backend/app/services/rule_engine.py), [rules.py schema](../backend/app/schemas/rules.py), [rules.py API](../backend/app/api/routes/rules.py) |
| Gửi lệnh và idempotency | [command_dispatch.py](../backend/app/services/command_dispatch.py), [commands.py](../backend/app/api/routes/commands.py), [background_tasks.py](../backend/app/services/background_tasks.py) |
| Config và ACK | [configs.py](../backend/app/api/routes/configs.py), [config_publish_service.py](../backend/app/services/config_publish_service.py), [mqtt_service.py](../backend/app/services/mqtt_service.py) |
| Lịch sử/thống kê | [history.py](../backend/app/api/routes/history.py), [latency.py](../backend/app/services/latency.py), [schema history](../backend/app/schemas/history.py) |
| WS/vận hành | [ws_tickets.py](../backend/app/services/ws_tickets.py), [websocket_manager.py](../backend/app/services/websocket_manager.py), [main.py](../backend/app/main.py), Dockerfile/Compose |
| Firmware TV1 giữ từ main | [config_store.cpp](../firmware/esp32-alert-node/src/app/config_store.cpp), [bàn giao TV1](../firmware/esp32-alert-node/tuan3-ban_giao.md). Không thay bản TV1 bằng config_manager cũ của TV2. |
| FE | [DeviceHistoryPanel.jsx](../frontend/src/components/DeviceHistoryPanel.jsx), [history.js](../frontend/src/services/history.js), header idempotency và trạng thái config |
| Minh chứng tự động | [test_week3_integration.py](../backend/tests/test_week3_integration.py), [runner DB riêng](../backend/tests/run_week3_integration.py), [verify_week3.py](../backend/scripts/verify_week3.py) |

AI tiếp tục dùng topic/payload đang có; code tuần 3 đọc và lưu thêm thông tin cần thiết từ sự kiện. Các lệnh gửi ESP32 vẫn là LED_ON/BUZZER_ON/MOTOR_ON và intensity WEAK/MEDIUM/STRONG đang được firmware hiểu.

## 5. Những việc cần nhóm xác nhận và test tiếp

1. TV1/TV3 xác nhận ngưỡng severity, cooldown, thời lượng tải, tuổi sự kiện được phép điều khiển và quan hệ camera → ESP32; sau đó mới bật Rule Engine ngoài môi trường test.
2. TV1 xác nhận schema config đang dùng, nạp firmware development lên ESP32 thật và thử nhận/lưu/reboot/applied; bổ sung chống config cũ đến lại và kiểm tra nội dung khi trùng ID. Lệnh đang chạy giữ timing đã lấy khi bắt đầu; cần xác nhận trên board thật.
3. Test lệnh/ACK với LED, còi, motor thật. Firmware cần được kiểm chứng chống thực thi lệnh trùng trước khi cân nhắc tự retry lệnh MQTT.
4. TV4 duyệt hợp đồng API và thao tác lịch sử/thống kê trên trình duyệt với dữ liệu của nhóm.
5. Nhóm đối chiếu lại mã W3 theo bảng tích hợp chính thức và bổ sung ảnh/video phần cứng. Chưa có các ảnh/video đó trong bộ minh chứng này.
6. Nếu triển khai nhiều worker/nhiều BE, cần thay kho ticket RAM và kênh phát sự kiện bằng thành phần dùng chung; hiện Docker chạy một worker.

## 6. Tệp bàn giao và cách kiểm tra lại

- [Giải thích logic và hợp đồng API/WS](TV2-tuan-3-huong-xu-ly-va-logic-code.md).
- [OpenAPI JSON](evidence/week3/openapi.json), dùng cùng `/api/openapi.json` và `/docs` khi BE đang chạy.
- [ACL mẫu không có mật khẩu](evidence/week3/acl-policy.json).
- [Kết quả tích hợp có từng quan sát](evidence/week3/integration-results.json).
- [Kết quả kiểm tra build/test](evidence/week3/verification-results.json).

Các lệnh tái hiện đã ghi trong tài liệu logic. Phiên bản mã nguồn được theo dõi bằng lịch sử commit của nhánh bàn giao. File báo cáo, hợp đồng và minh chứng được commit; `.env`, cấu hình mạng riêng và bản sao local được ignore. Minh chứng này chưa thay cho nghiệm thu chung của bốn thành viên.

## 7. Người phụ trách BE tuần sau bắt đầu từ đâu?

1. **Chạy lại môi trường:** lấy nhánh bàn giao, cấu hình `.env` riêng, chạy migration tuần 2 rồi tuần 3 theo hướng dẫn. Kiểm tra đăng nhập, health và broker. Không chạy `create.sql` trên DB có dữ liệu.
2. **Chốt với TV3:** loại event, trường `device_id` đang chứa mã Vision Node, thời điểm gửi tiếp khi buồn ngủ kéo dài, sự kiện mất tập trung và đề xuất topic theo thiết bị. Chưa đổi topic AI trong bản này; khi đổi cần cập nhật cả routing BE và ACL đang có tại broker.
3. **Chốt với TV1/TV3:** mức cảnh báo, thời lượng/tải, liên kết camera–ESP32, cooldown có cho tăng mức hay không và giới hạn tuổi sự kiện. Sau khi test mới bật công tắc toàn hệ thống và binding; không bật chỉ vì test giả lập đã đạt.
4. **Hoàn tất cấu hình với TV1:** xử lý revision/config trùng ID như TV2-10; thử mất mạng, reboot, config cũ và config khi lệnh đang chạy. ACK hiện QoS 0; BE chưa tự gửi lại lệnh khi mất ACK. Nếu chọn retry cùng request_id, cần chốt thời gian/số lần và kiểm chứng request log firmware trước.
5. **Xác nhận API với TV4:** API phân trang dùng `/api/devices/{id}/...`; biểu đồ dùng `/api/{id}/telemetry/history`. Kiểm tra ba role trên trình duyệt, lọc UTC/phiên bản AI và reconnect.
6. **Nghiệm thu chung:** đối chiếu mã W3 chính thức, chạy với AI/camera và ESP32 thật, ghi request_id/event_id cùng ảnh/video/log đã che thông tin đăng nhập; cập nhật trạng thái mục 2 theo minh chứng mới.

Các entry point nên đọc trước: `mqtt_service.process_message` → `rule_engine.process_event` → `command_dispatch` → `background_tasks`; API lệnh/config/history/rules và hai tài liệu tuần 3. Khi một ca lỗi, đọc kết quả gốc trong `docs/evidence/week3`, sửa đúng luồng rồi chạy lại ca liên quan.

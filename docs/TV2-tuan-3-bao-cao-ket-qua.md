# Báo cáo kết quả thực hiện Backend tuần 3 — TV2

**Bổ sung 21/10/2026:** [kết quả cập nhật event/video và môi trường](BE-ai-event-video-ket-qua.md).
Các bảng ngày 19/10 bên dưới là kết quả đợt bàn giao trước; minh chứng trong
`docs/evidence/week3` đã được cập nhật bằng lần kiểm tra mới nhất.

**Cập nhật:** 19/10/2026, múi giờ Asia/Bangkok. **Phạm vi:** TV2-01 đến TV2-23; gồm các việc hoàn thiện tuần 2 và phần phát triển tuần 3. **Nhánh bàn giao:** `feature/backend-week3`, đồng bộ main đến `bf08133` gồm FE, firmware TV1 và Edge AI mới. Nguyên nhân conflict và kết quả đối chiếu ba phần ở mục 8.

**Lần chạy tích hợp kết thúc:** 19/10/2026 22:31:40 (UTC+07:00), trên broker và DB thử riêng.

TV2-01 đến TV2-04 được đối chiếu với code và minh chứng. Lần resolve PR #5 chạy lại bộ tích hợp, bổ sung các ca 17–21 cho hợp đồng AI mới. Những mục còn thiếu bằng chứng trình duyệt/phần cứng vẫn được giữ trạng thái một phần.

**Kết luận:** phần code BE và các ca kiểm tra bên dưới đạt. Chưa thể đánh dấu hoàn thành toàn bộ tuần 3 vì còn chốt chính sách AI, hợp đồng với TV1/TV4 và kiểm tra phần cứng. Bảng nhiệm vụ ở mục 2 ghi rõ từng giới hạn; mục 7 dành cho người tiếp nhận BE tuần sau.

Code được kiểm tra với PostgreSQL thật, broker MQTT Docker thật dùng riêng cho test, HTTP/WebSocket và container BE được restart. Các hàm tạo payload, SQLite và MQTT client hiện tại của AI đã được kiểm tra không mở camera. ESP32 là client giả lập; pipeline OpenCV/MediaPipe và còi/đèn/motor thật chưa được chạy trong đợt này.

**Môi trường đang dùng chưa được nâng cấp:** kiểm tra chỉ đọc cho thấy thiếu bảng `ai_message_receipts` và quyền topic mới ở broker. Thao tác đổi ACL trực tiếp bị bộ duyệt tự động từ chối; test chuyển sang broker riêng, không thay quyền hiện có. Xem [runtime-readiness.json](evidence/week3/runtime-readiness.json) và hướng dẫn áp dụng sau khi nhóm duyệt ở mục 8.4.

Nhóm xác nhận **chưa chốt severity, cooldown và bảng W3**. Chính sách mẫu đã có code nhưng `RULE_ENGINE_ENABLED` mặc định `false`. Các giá trị mẫu và cách gán mã ca test trong tài liệu chưa được coi là thống nhất chính thức của TV1/TV3/TV4.

Tài liệu giải thích logic, hợp đồng JSON và cách chạy: [Hướng xử lý và logic code](TV2-tuan-3-huong-xu-ly-va-logic-code.md).

## 1. Kết quả kiểm tra có minh chứng

| Kiểm tra | Kết quả đã ghi nhận | Minh chứng gốc |
| --- | --- | --- |
| Test BE thông thường | 56 test được phát hiện; **34 chạy đạt**, 22 bỏ qua có chủ đích vì cần chế độ live riêng | [unit-output.txt](evidence/week3/unit-output.txt) |
| Tích hợp tuần 3 | **21/21 đạt; 0 lỗi; 0 bỏ qua**, có Docker restart và storage_ack | [integration-output.txt](evidence/week3/integration-output.txt), [integration-results.json](evidence/week3/integration-results.json) |
| ACL trên broker thật | **1/1 đạt** trên broker Docker thử riêng; có kiểm tra quyền AI mới, gửi chéo và thu hồi | [acl-output.txt](evidence/week3/acl-output.txt), [acl-results.json](evidence/week3/acl-results.json) |
| Test FE | **59/59 đạt** | [frontend-tests-output.txt](evidence/week3/frontend-tests-output.txt) |
| Build FE | Thành công | [frontend-build-output.txt](evidence/week3/frontend-build-output.txt) |
| Build firmware | PlatformIO môi trường **development SUCCESS** | [firmware-build-output.txt](evidence/week3/firmware-build-output.txt) |
| Migration DB đang cấu hình | Bản trước lần resolve đã thêm ai_events/rule_bindings. Bảng biên nhận mới chưa áp dụng vào DB ứng dụng; đã kiểm tra trên DB thử | [migration-results.json trước đó](evidence/week3/migration-results.json), [trạng thái hiện tại](evidence/week3/runtime-readiness.json) |
| Migration chạy lại | Được chạy hai lần trên DB thử trước test, không lỗi | [run_week3_integration.py](../backend/tests/run_week3_integration.py), kết quả tích hợp ở trên |
| Cấu hình Compose | Kiểm tra `config -q` đạt, không in mật khẩu | [compose-results.json](evidence/week3/compose-results.json) |
| Dọn tài nguyên thử | Còn 0 database thử và 0 container thử; Rule Engine trên máy đang tắt | [resource-cleanup.json](evidence/week3/resource-cleanup.json) |
| Module AI hiện tại | Hai tin được giữ trong SQLite khi chưa có kết nối, gửi khi kết nối lại và xóa sau storage_ack | [edge-queue-output.txt](evidence/week3/edge-queue-output.txt), test 20 |

Các test live tạo database riêng tên `codex_w3_...`, tài khoản MQTT thử và container BE riêng, rồi tự dọn tài nguyên thử. DB ứng dụng không bị khởi tạo lại. Migration trên DB ứng dụng chỉ thêm bảng/cột/chỉ mục.

## 2. Kết quả theo từng đầu việc

| Mã | Phần đã thực hiện và kiểm chứng | Trạng thái và giới hạn |
| --- | --- | --- |
| **TV2-01** | Compose có PostgreSQL, Mosquitto, BE, FE; BE chờ migration và tạo tài khoản MQTT. Test tích hợp dùng PostgreSQL/broker thật, BE Docker riêng; FE build đạt; migration tuần 3 đã chạy trên DB đang cấu hình và chạy lại trên DB thử | **Một phần**: các thành phần và migration có minh chứng, nhưng chưa có kết quả mở FE trong bộ Compose đầy đủ rồi thao tác qua FE → BE → MQTT/DB. `config -q` chỉ kiểm tra cấu hình, không chứng minh cả hệ thống đã chạy cùng nhau. Xem mục 3.6. |
| **TV2-02** | Có health/login/me, lọc thiết bị theo gán, kiểm tra role, vé WS và lọc sự kiện theo quyền. Test 12 kiểm tra health/login Admin qua HTTP thật, WS được gán/không được gán và thu hồi quyền; test thông thường kiểm tra ranh giới cả ba role | **Một phần**: chưa có ma trận đăng nhập → API → WS thật đầy đủ cho cả Admin, Employee, Customer. Có test role Employee trong code nhưng không được coi là đã chạy trọn luồng Employee qua HTTP/WS. Xem mục 3.6. |
| **TV2-03** | Broker yêu cầu tài khoản/ACL; setup mới cập nhật role BE/AI đã tồn tại, giữ mật khẩu và trạng thái bị thu hồi. Có API cấp quyền theo loại Vision/Alert Node | **Đạt code và broker thử riêng**. [ACL PASS](evidence/week3/acl-output.txt), test 01/17/20. Bộ quyền mới chưa áp dụng vào broker đang dùng; còn kiểm tra AI/camera và ESP32 thật. |
| **TV2-04** | ESP32 có nhánh command/config/status/ACK/applied riêng; AI có nhánh telemetry/events/status và chỉ đọc storage_ack của nó. Chặn nguồn JSON khác topic; tài khoản AI mặc định giữ quyền gửi topic chung cũ để tương thích | **Đạt các ca quyền topic trên broker thử**, gồm quyền AI mới và chặn gửi/đọc chéo. Kênh chung cũ chưa phân tách nguồn nhiều camera hoàn toàn; còn kiểm chứng trên chương trình camera/board thật. |
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
| **TV2-15** | Rule Engine nhận cả hợp đồng cũ và message_id/device_code mới; lưu event → alert → command; test topic mới đi tới ba ACK và API/WS FE | **Đạt luồng DROWSY trong môi trường thử**, test 06/13/21. DISTRACTED đã lưu nhưng policy điều khiển còn chờ chốt; chưa chạy tải thật. |
| **TV2-16** | Unique event_id và biên nhận device/message trong PostgreSQL; gửi đồng thời/process mới không tạo trùng dữ liệu; ACK mất được trả lại khi gửi lại | **Đạt phía BE**, test 07/17/19. |
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
| HTTP phía BE | 132.650 ms |
| Tổng tới khi đủ COMPLETED | 196.800 ms |
| MQTT publish của LED | 22.899 ms |
| Bắt đầu publish tới ACK LED | 146.371 ms |

Đây là minh chứng cơ chế đo đang hoạt động. Không dùng các giá trị của thiết bị giả lập này để kết luận độ trễ thực tế của còi/rung trên ESP32.

### 3.3. Rule Engine đi hết luồng qua MQTT

Test 13 kiểm tra tương thích topic AI cũ `driver/events`; BE lưu quyết định và lệnh; worker phát ba lệnh; ESP32 giả lập gửi đủ ACK. Mẫu liên kết: event `event-d7c09050864dbbe0` → alert `11` → request `cmd-11`, mức 2/MEDIUM, ACK cuối COMPLETED. Gửi lại event không phát thêm lệnh. Topic mới theo mã thiết bị được kiểm tra riêng ở test 21.

Test 07 gửi đồng thời cùng event rồi phát lại từ một process Python mới, kết quả vẫn chỉ có một event, một alert và một lệnh cha. Test 14 giả lập BE dừng sau khi đã ghi dấu PUBLISHING, xác nhận session mới không gửi lại mù và cuối cùng ghi TIMEOUT với thông tin kết quả gửi chưa xác định.

Các event mức 2/3 trong test mang thời lượng giả lập tương ứng. AI thực tế hiện theo hướng gửi một event khi đạt 3 giây; chưa thể kết luận tăng mức theo thời gian đã chạy trọn luồng. Cooldown hiện chặn cả event mức cao hơn trong khoảng chờ. Đây là hai điểm cần thống nhất trước khi bật Rule Engine.

### 3.4. Restart Docker và WebSocket

Test 12 mở WebSocket thật tới container BE riêng bằng hai tài khoản. Tài khoản được gán nguồn nhận device.updated; tài khoản không được gán không nhận. Sau khi thu hồi gán thiết bị trong PostgreSQL, socket đang mở ngừng nhận dữ liệu nguồn. Vé dùng lại/hết hạn bị từ chối. Sau restart container, xin vé mới để kết nối lại và nhận trạng thái thiết bị.

Sau restart, API vẫn trả lệnh COMPLETED, config đã applied, lịch sử, alert và timeline event. POST cùng idempotency key vẫn trả request_id cũ. Log container được che giá trị ticket: [docker-be-output.txt](evidence/week3/docker-be-output.txt).

### 3.5. Đồng thời và ACK reboot theo firmware mới

Test 15 gửi đồng thời hai PUT cấu hình đầu tiên: cả hai HTTP 200, DB chỉ có một dòng cấu hình, revision cuối bằng 2; tin retained khớp config_id desired cuối. Test 16 gửi `INTERRUPTED` với lỗi `REBOOTED` qua broker thật: lệnh cha chuyển FAILED, giữ lỗi REBOOTED và không báo COMPLETED. Hai ca này được ghi trong integration-results.json.

### 3.6. Minh chứng và phần cần kiểm tra tiếp của TV2-01 đến TV2-04

| Mã | Minh chứng có thể mở để đối chiếu | Việc còn lại trước khi nghiệm thu đầy đủ |
| --- | --- | --- |
| TV2-01 | [Compose](../deployment/docker-compose.yml), [config hợp lệ](evidence/week3/compose-results.json), [migration DB](evidence/week3/migration-results.json), [FE build](evidence/week3/frontend-build-output.txt), test 12 trong [kết quả tích hợp](evidence/week3/integration-results.json) | Chạy đủ FE/BE/PostgreSQL/Mosquitto từ Compose và thao tác trên trình duyệt. Test migration nâng từ tuần 2 và chạy lại đã có; khi áp dụng cho DB khác cần kiểm tra dữ liệu trước/sau tại DB đó. |
| TV2-02 | [Test role và hợp đồng](../backend/tests/test_week2_contract.py), [unit PASS](evidence/week3/unit-output.txt), test 09/10/12 trong [kết quả tích hợp](evidence/week3/integration-results.json), [log WS đã che vé](evidence/week3/docker-be-output.txt) | Đăng nhập thật từng role, xem thiết bị được gán, gọi API thiết bị không được gán; kiểm tra quyền gửi lệnh/sửa cấu hình và sự kiện WS. Admin cũng phải được gán thiết bị, không mặc định xem toàn bộ. |
| TV2-03 | [Cấu hình broker](../deployment/mqtt/mosquitto.conf), [khởi tạo tài khoản](../backend/app/services/mqtt_bootstrap.py), [ACL PASS](evidence/week3/acl-output.txt), test 01 provision/revoke | TV1/TV3 dùng credential riêng trên ESP32/AI thật, đúng IP/cổng; lưu bằng chứng kết nối và nhận/gửi tin đã che mật khẩu. Broker Docker dùng cổng 1884 trên Windows, khác broker Windows cổng 1883 nếu còn chạy. |
| TV2-04 | [Mẫu quyền](evidence/week3/acl-policy.json), [test broker thật](../backend/tests/test_mqtt_security_integration.py), [ACL PASS](evidence/week3/acl-output.txt) | Duyệt áp dụng bộ quyền mới trên broker đang dùng, rồi kiểm tra tài khoản thật sau khi nạp firmware/AI; routing và ACL nguồn đã được cập nhật cho topic AI mới. |

Test 12 tạo tài khoản Admin và Customer thử; kiểm tra thêm việc đổi Admin sang Customer bị chặn gửi lệnh. Nó chưa thay cho một bộ test ba tài khoản riêng đủ mọi chức năng. Test ACL dùng mã thiết bị tạm `tv2-security-...`, không điều khiển board `alert-01` thật.

## 4. Các thay đổi code chính

| Nhóm code | File tiêu biểu |
| --- | --- |
| Môi trường và migration tuần 2 | [docker-compose.yml](../deployment/docker-compose.yml), [migration_fe_be_week2.sql](../database/migration_fe_be_week2.sql), Dockerfile BE/FE và [hướng dẫn triển khai](../deployment/README.md) |
| Đăng nhập, quyền API và tài khoản MQTT | [users.py](../backend/app/api/routes/users.py), [deps.py](../backend/app/api/deps.py), [access.py](../backend/app/services/access.py), [mqtt_bootstrap.py](../backend/app/services/mqtt_bootstrap.py), [mqtt_security.py](../backend/app/services/mqtt_security.py) |
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

Với TV2-01 đến TV2-04, cần hoàn tất bằng chứng chạy đủ bộ Compose, ma trận HTTP/WS ba role và xác nhận tài khoản/quyền topic từ TV1/TV3 theo mục 3.6.

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

1. **Chạy lại môi trường và bổ sung TV2-01…04:** lấy nhánh bàn giao, cấu hình `.env` riêng, chạy migration tuần 2 rồi tuần 3 theo hướng dẫn. Kiểm tra health, đầy đủ FE/BE/DB/broker, HTTP/WS ba role và quyền topic với TV1/TV3 theo mục 3.6. Không chạy `create.sql` trên DB có dữ liệu.
2. **Chốt với TV3:** dùng luồng `edge-ai/main2.py` có SQLite, topic theo mã và `message_id/device_code`. Code BE đã nối storage_ack; môi trường đang dùng cần duyệt áp dụng migration/ACL mới theo mục 8.4. Còn chốt nhịp gửi event khi buồn ngủ kéo dài và policy cho mất tập trung.
3. **Chốt với TV1/TV3:** mức cảnh báo, thời lượng/tải, liên kết camera–ESP32, cooldown có cho tăng mức hay không và giới hạn tuổi sự kiện. Sau khi test mới bật công tắc toàn hệ thống và binding; không bật chỉ vì test giả lập đã đạt.
4. **Hoàn tất cấu hình với TV1:** xử lý revision/config trùng ID như TV2-10; thử mất mạng, reboot, config cũ và config khi lệnh đang chạy. ACK hiện QoS 0; BE chưa tự gửi lại lệnh khi mất ACK. Nếu chọn retry cùng request_id, cần chốt thời gian/số lần và kiểm chứng request log firmware trước.
5. **Xác nhận API với TV4:** API phân trang dùng `/api/devices/{id}/...`; biểu đồ dùng `/api/{id}/telemetry/history`. Kiểm tra ba role trên trình duyệt, lọc UTC/phiên bản AI và reconnect.
6. **Nghiệm thu chung:** đối chiếu mã W3 chính thức, chạy với AI/camera và ESP32 thật, ghi request_id/event_id cùng ảnh/video/log đã che thông tin đăng nhập; cập nhật trạng thái mục 2 theo minh chứng mới.

Các entry point nên đọc trước: `mqtt_service.process_message` → `rule_engine.process_event` → `command_dispatch` → `background_tasks`; API lệnh/config/history/rules và hai tài liệu tuần 3. Khi một ca lỗi, đọc kết quả gốc trong `docs/evidence/week3`, sửa đúng luồng rồi chạy lại ca liên quan.

## 8. Resolve PR #5 và đối chiếu BE với ba phần còn lại

### 8.1. Nguyên nhân conflict và cách giải quyết

PR [#5](https://github.com/toanhy189/Driver-Monitoring-AIoT-Platform/pull/5) đưa nhánh BE vào main. Main có hai commit AI mới `a6da8a5` và `bd73636`: đổi `drowsiness-detection` thành `edge-ai`, thay cấu hình và thêm SQLite/storage_ack. Nhánh BE lại sửa `drowsiness-detection/config.py` để đọc tài khoản từ `.env`. Git báo **modify/delete** tại đúng file đó: một phía sửa, phía kia xóa khi chuyển cấu trúc.

Cách resolve: giữ cấu trúc edge-ai và topic mới của TV3, chuyển phần đọc `.env` sang `edge-ai/config.py`, bỏ đường dẫn cũ. Không khôi phục cả hai cây thư mục. File SQLite hàng đợi được giữ trên máy và bỏ khỏi file commit; không viết lại lịch sử main đã chứa nó.

### 8.2. Các điểm chưa khớp đã nối lại

- BE nhận thêm `driver/{code}/events`; nhận nguồn `device_code` và lấy message_id làm event_id khi cần.
- Thêm `ai_message_receipts` để lưu dữ liệu và xác nhận trong cùng transaction; chỉ trả SAVED sau commit, gửi lại không tạo bản ghi trùng. Kiểm tra JSON khớp topic; lỗi schema/commit hoặc ID trùng khác nội dung không được xác nhận đã lưu.
- ACL mới cho BE gửi storage_ack và AI chỉ đọc xác nhận của chính nó; setup cập nhật role có sẵn thay vì chỉ tạo mới. Chưa áp dụng lên broker đang dùng.
- Luồng main2 ghi SQLite trước rồi gửi bằng một worker; đóng client dừng worker. Event có model_version; FE giữ phiên bản BE trả và hiển thị “Chưa cung cấp” khi thiếu.
- Chỉ điều chỉnh phần cấu hình/giao tiếp và kiểm thử không camera; không đổi thuật toán mắt, khuôn mặt, head pose hay firmware TV1.

### 8.3. Kết luận theo từng phần

| Cặp tích hợp | Kết quả kiểm tra | Giới hạn còn lại |
| --- | --- | --- |
| **BE ↔ FE (TV4)** | API thiết bị/số đo/lịch sử/lệnh/config, quyền và WS tiếp tục đạt; 59 test FE và build đạt. Test 21 xác nhận sự kiện topic mới tạo alert.created và liên kết API alert → command hoàn tất | Chưa nghiệm thu thao tác toàn bộ FE trong Compose bằng trình duyệt thật hoặc ma trận HTTP/WS đủ ba role |
| **BE ↔ AI (TV3)** | Test 17–20 kiểm tra topic mới, message_id, storage_ack, SQLite thật, lost ACK, DB lỗi, duplicate, process mới và replay cũ. Test 21 nối DROWSY mới qua rule đến ACK/WS | Chưa áp dụng DB/ACL ở môi trường đang dùng; chưa chạy camera/OpenCV/MediaPipe. Một event 3 giây chưa đủ tăng mức 6/10 giây; cooldown và policy DISTRACTED chưa được nhóm chốt |
| **BE ↔ IoT (TV1)** | Topic và payload command/config/ACK giữ đúng firmware trên main; ba ACK con, INTERRUPTED/REBOOTED, timeout, config APPLIED/REJECTED đạt với client giả lập. Firmware development build đạt | ESP32 thật chưa được thử trong đợt này. Firmware chưa chống config revision cũ/ID trùng khác nội dung; ACK QoS 0 có thể mất và BE chưa tự retry cùng request_id |

**Kết luận:** đã nối và kiểm chứng hợp đồng giao tiếp trong môi trường thử; chưa thể kết luận toàn bộ tuần 3 hoặc hệ thống đang dùng đã hoàn tất nghiệm thu.

### 8.4. Áp dụng và chạy lại kiểm tra

Minh chứng mới: [kết quả 21 ca](evidence/week3/integration-results.json), [module SQLite/MQTT AI](evidence/week3/edge-queue-output.txt), [ACL thử](evidence/week3/acl-results.json), [trạng thái môi trường đang dùng](evidence/week3/runtime-readiness.json).

Chạy lại không thay broker hiện có:

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml build mqtt-setup
python backend/tests/run_week3_isolated.py
python backend/scripts/verify_week3.py --firmware
```

Để áp dụng môi trường đang dùng sau khi nhóm duyệt: chạy migration tuần 3 mới để thêm ai_message_receipts, build/chạy lại mqtt-setup để cập nhật ACL và khởi động lại BE. Lệnh cụ thể trong [backend/README.md](../backend/README.md#áp-dụng-bản-đồng-bộ-ai-tuần-3). Bước kiểm tra hiện tại không ghi thay đổi vào DB ứng dụng hoặc ACL thật; bộ duyệt tự động đã từ chối thay ACL trên broker hiện hữu, nên phần kiểm chứng dùng broker thử riêng có mật khẩu ngẫu nhiên và tự dọn tài nguyên.

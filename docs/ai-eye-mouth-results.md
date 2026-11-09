# Kết quả AI mắt và miệng — 10/11/2026

## Trạng thái

Phiên bản `eye-mouth-fusion-20261110-134299e429cb`: **EXPERIMENTAL_OFFLINE_ONLY**. Backend và FE đã hỗ trợ số đo mới; bản RF đã thử camera vẫn có launcher riêng. Ứng viên mới chưa được nghiệm thu trên webcam của người dùng khi đeo kính hoặc cùng tải ESP32 thật, chưa thay mặc định.

Nhánh ngáp có thể dùng để thử tiếp. Độ nhận diện mắt, khoảng mất quan sát và cảnh báo nhầm còn hạn chế; chưa đủ cơ sở tuyên bố đã sửa xong vấn đề kính.

## Dữ liệu và huấn luyện

- NTHU từ ba archive cục bộ: **354 video hợp lệ, 88.809 thời điểm ở 3 Hz, 18 người**. Đọc nhãn gốc, không suy từ MAR hay tên hành vi.
- CNN: 10 người/199 video; fusion: 4 người/75 video; validation: 4 người/80 video. Người fit CNN không fit fusion.
- CNN fit 19.594 crop được cân bằng theo người/lớp; validation có 32.489 crop mắt/miệng. Số crop không phải số người hay thử nghiệm độc lập.
- Loại 22 video: 21 lệch frame/nhãn, một lỗi nhãn phụ. **Cả 20 video test gốc đều bị loại**, nên không có điểm test cuối hợp lệ.
- MobileNetV3 Small khởi tạo ImageNet; một epoch học head, ba epoch fine-tune block cuối, rồi sáu epoch toàn backbone. Chọn checkpoint bằng trung bình macro F1 mắt/miệng trên validation; giữ epoch 4 của lượt toàn backbone. Không dùng clip YawDD+ bên dưới để chọn model/ngưỡng.
- Mắt: `NORMAL/SLEEPY`; miệng: `NORMAL/YAWN/TALKING_LAUGHING`. `SLEEPY` không phải nhãn đóng/mở mí. Không giám sát mắt bằng ảnh kính râm; runtime chưa tự nhận biết kính râm.

## Validation của các thành phần

| Thành phần | Macro F1 | Phạm vi |
|---|---:|---|
| CNN mắt | 0,6692 | Crop hợp lệ, bỏ mắt kính râm |
| CNN miệng, ba lớp | 0,8330 | Crop hợp lệ, gồm nói/cười |
| RF kết hợp, nhị phân | 0,8134 | 15.035 cửa sổ được chấp nhận |

RF dùng 28 đặc trưng mắt/miệng/EAR/MAR/hướng đầu và độ phủ từng kênh; cửa sổ tối đa 5 giây, tối thiểu 2 giây lịch sử. Nhãn cửa sổ cần ít nhất 80% thời gian cùng nhãn; đoạn chuyển tiếp/thiếu dữ liệu có thể bị loại khỏi bảng này. Các cửa sổ chồng lấn có tương quan.

Ngưỡng RF chọn trên validation: **0,6**. Accuracy cửa sổ 81,63%; recall buồn ngủ 76,35%; false positive rate lớp âm 9,92%. Riêng cửa sổ `glasses`: macro F1 0,8096, recall buồn ngủ 68,02%. Đây chưa phải camera RGB của người dùng.

## Replay toàn video và policy

Replay cả 80 video validation, giữ mất mặt/kênh và warmup. Áp dụng `AlertPolicy` hiện có, gồm xác nhận trạng thái và mức 3/6/10 giây; không gửi MQTT hay điều khiển tải.

| Chỉ số | Kết quả |
|---|---:|
| Thời gian có nhãn được tính | 6.671 giây |
| Thời gian candidate UNKNOWN | 36,42% |
| Thời gian nhãn buồn ngủ được nhận DROWSY, UNKNOWN tính bỏ sót | 54,22% |
| Đoạn buồn ngủ ≥3,5 giây có cảnh báo | 61/82 (74,39%) |
| Đoạn đủ dài bị bỏ sót | 21 |
| Episode cảnh báo DROWSY nhầm trên nhãn âm | 4 |
| Tỷ lệ nhầm quy đổi trên 0,783 giờ nhãn âm | 5,11 episode/giờ |
| Delay cảnh báo median / p95 từ đầu đoạn nhãn | 5,05 / 25,66 giây |

Nhãn lấy mẫu ở 3 Hz; không nội suy qua gap >0,5 giây. Đoạn ngắn vẫn nằm trong recall theo thời gian nhưng không nằm trong recall cảnh báo theo đoạn. Chỉ chấm DROWSY với nhãn buồn ngủ, chưa chấm DISTRACTED. Hiệu chuẩn đầu giả định nhìn thẳng lúc khởi động; NTHU không bảo đảm điều kiện đó.

**Đây là lý do giữ trạng thái thử nghiệm.** Không kéo dài DROWSY hoặc bỏ UNKNOWN để làm đẹp kết quả. Replay vẫn dùng validation đã chọn model; không thay test độc lập, thử webcam hay đo thời điểm tải hoạt động.

## Kiểm tra ngáp trên nguồn khác

Đã tải nhãn frame của [YawDD+ từ kho tác giả](https://opensource.silicon-austria.com/mujtabaa/yawdd), commit `222e94371df161bd673fcec4a1a755afef18ddd7`, cùng một clip mẫu sạch, không có nhãn vẽ lên hình. Chưa tải toàn bộ video YawDD gốc. Dữ liệu dành cho nghiên cứu phi thương mại theo điều khoản nguồn.

Clip `1-FemaleNoGlasses-Yawning`: đúng 387 frame và 387 nhãn, gồm 294 không ngáp và 93 ngáp. Class lấy từ cột đầu nội dung YOLO; hậu tố `_0` trong tên file không phải class. Script khóa checksum của archive và video.

- Có crop miệng ở 384/387 frame (99,22%).
- Top-1 trên crop, gộp bình thường/nói/cười thành không ngáp: **macro F1 nhị phân 0,8673**, accuracy 89,58%.
- Cổng confidence runtime 0,6: nhận ngáp đúng **81/93 frame (87,10%)**, tính UNKNOWN vào bỏ sót; UNKNOWN 26/387 frame (6,72%).

| Nhãn thật | Không ngáp | Ngáp | UNKNOWN |
|---|---:|---:|---:|
| Không ngáp | 250 | 26 | 18 |
| Ngáp | 4 | 81 | 8 |

Chỉ có một clip ngoài NTHU, không kính; các frame có tương quan. Trọng số/ngưỡng giữ nguyên trước lượt này. Không gọi đây là đánh giá buồn ngủ, kính, cả ba lớp miệng hay toàn bộ YawDD+; không thay test cuối hệ thống.

## Tốc độ trên laptop

Hai đoạn NTHU 20 giây, chạy CPU, PyTorch đặt hai thread, 100 thời điểm/đoạn ở 5 Hz. MediaPipe và RF còn có các luồng riêng.

| Điều kiện | Pipeline trung bình | Pipeline p95 | RSS đỉnh |
|---|---:|---:|---:|
| Không kính | 33,4 ms | 67,0 ms | 788 MiB |
| Có kính | 34,3 ms | 73,3 ms | 802 MiB |

Pipeline gồm landmark, CNN, hình học, fusion và policy. Throughput video ghi sẵn khoảng 25 thời điểm/giây, không chờ theo thời gian thực; **không gọi đây là FPS webcam**. Chưa tính render, encode, MQTT/HTTP hoặc âm thanh; không chứng minh đã nghiệm thu kính.

## Tương thích và bước tiếp theo

Đã kiểm tra schema hữu hạn, snapshot/history, WebSocket, UI Customer, mất mặt và biểu đồ có gap. Số đo thật từ checkpoint đã đi qua MQTT có xác thực, PostgreSQL và API trong môi trường riêng. ESP32 giữ LED_ON/BUZZER_ON/MOTOR_ON, TTL và ACK; phần mở rộng telemetry không cần đổi firmware.

Trước khi đổi bản demo mặc định, cần phiên RGB mới có/không kính: mở mắt tự nhiên, nhắm mô phỏng, ngáp, nói/cười, mở lại, quay đầu và che camera. Ghi báo nhầm/bỏ sót/UNKNOWN và delay. Phiên fine-tune không được làm test cuối. Cần xử lý nguồn test lỗi hoặc bổ sung người/phiên có nhãn mới; không kéo giãn nhãn tùy ý.

Xem [thiết kế và hướng dẫn chạy](ai-eye-mouth-model.md). JSON chi tiết và bundle nằm ở `edge-ai/ml-runs/multisignal-20261110/candidate/` cục bộ, được Git ignore.

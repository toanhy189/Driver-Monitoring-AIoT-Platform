# Đánh giá độ chính xác điểm mốc khuôn mặt (Facial Landmark Benchmark)

Thư mục này chứa notebook `detection_ai.ipynb` và mô-đun `landmark_metrics.py` phục vụ đánh giá sai số định vị 5 điểm mốc khuôn mặt cơ bản (hai mắt, mũi, hai khóe miệng) trên tập ảnh tĩnh.

## Lưu ý kỹ thuật khi chạy đánh giá

- Sử dụng chế độ xử lý ảnh tĩnh `IMAGE` (`detect()`) thay vì chế độ chuỗi video (`detect_for_video()`).
- Sắp xếp tọa độ dự đoán và nhãn gốc (`ground truth`) theo cùng chiều trục hoành `x` trên ảnh cho cặp mắt và khóe miệng.
- Loại trừ tường minh các mẫu không hợp lệ hoặc có khoảng cách liên đồng tử bằng `0`.
- Báo cáo đầy đủ tỷ lệ phát hiện khuôn mặt (`detection coverage`) và sai số chuẩn hóa `NME` (Normalized Mean Error) trên tập giao phát hiện được.
- Tốc độ `FPS` đo trong notebook chỉ phản ánh thời gian suy luận điểm mốc đơn thuần; hiệu năng toàn luồng camera thời gian thực được đo riêng qua `ml.multisignal_benchmark`.

Mô-đun tính toán chỉ số `landmark_metrics.py` đã có bài kiểm thử tự động đi kèm trong `edge-ai/tests/`.

# Facial Landmark Model Benchmark

Notebook kiểm thử và so sánh 3 mô hình nhận diện khuôn mặt, trích xuất facial landmarks trên dataset [Facial Keypoints Detection](https://www.kaggle.com/competitions/facial-keypoints-detection/data).

**Model được kiểm thử:**
- MediaPipe Face Landmarker
- RetinaFace
- MTCNN

**Thang đánh giá:**
- Detection Rate
- Normalized Mean Error (NME)
- Mean Inference Time
- FPS (inference only)
- Errors

**Kết quả:** MediaPipe Face Landmarker được lựa chọn nhờ tỷ lệ phát hiện đạt 100% và thời gian suy luận trung bình chỉ khoảng 8,08 ms. Tỷ lệ phát hiện cao giúp giảm nguy cơ gián đoạn dữ liệu landmark, từ đó hạn chế các thay đổi trạng thái sai do thiếu dữ liệu đầu vào. Đồng thời, tốc độ suy luận nhanh đáp ứng tốt yêu cầu xử lý thời gian thực của hệ thống.
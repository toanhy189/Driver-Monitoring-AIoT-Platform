# Chẩn đoán báo DROWSY khi mở mắt — 08/11/2026

## Kết luận hiện tại

**RF đối chiếu chưa đạt ca camera thật.** Người dùng xác nhận mở mắt, nhìn thẳng nhưng vẫn thấy DROWSY sau hơn 30 giây. Log suy luận có các cửa sổ PERCLOS = 0, thời gian nhắm mắt dài nhất = 0 nhưng RF vẫn vượt ngưỡng 0,4. Không thể giải thích ca này chỉ bằng cửa sổ dữ liệu cũ.

Camera đã được người dùng đóng. Chưa thay model mặc định, artifact bàn giao hay policy `driver-bench-20261107-v1`. Các ứng viên ở thư mục thử nghiệm riêng; không sửa BE/FE để che kết quả nhận biết.

## So sánh đã thực hiện

Các model đều chọn bằng GroupKFold trên 14 người development. Dữ liệu mở mắt cá nhân không dùng để fit hoặc chọn ngưỡng trong các thử nghiệm này; tuy nhiên nó đã được xem để định hướng thử nghiệm, vì vậy chỉ là dữ liệu chẩn đoán đã biết.

| Bản thử | Recall / FPR development, trung bình theo người | Báo DROWSY trên 55 cửa sổ mở mắt đang kiểm tra | Quyết định |
|---|---|---|---|
| RF đối chiếu, 19 đặc trưng, ngưỡng 0,4 | 98,43% / 23,22% | 23 | Chưa đạt camera |
| RF chỉ đặc trưng mắt, ngưỡng 0,65 | 77,63% / 29,80% | 44 | Không thay bản chạy |
| SVM chỉ đặc trưng mắt, margin 0 | 78,26% / 28,70% | 36 | Không thay bản chạy |
| RF 7 đặc trưng mắt, ngưỡng 0,7 | 75,06% / 31,89% | 18 | Không đạt mục tiêu development |
| RF ưu tiên giảm báo nhầm, 19 đặc trưng, ngưỡng 0,75 | 84,02% / 9,58% | 0 | Ứng viên để thử tiếp, chưa nghiệm thu |

55 cửa sổ chồng lấn được lọc từ log có coverage ≥ 99%, PERCLOS = 0 và longest_closed_s = 0 trong phiên người dùng báo đang tỉnh. Đây không phải 55 người, 55 lần cảnh báo độc lập hay phép đo độ chính xác thực tế. Chưa có nhãn thời gian đầy đủ để tính sensitivity/recall trên camera; **0/55 không chứng minh hết báo nhầm**.

Ứng viên cuối được chọn lại từ các trial development đã có: FPR trung bình theo người ≤ 10%, recall ≥ 75%, rồi tối đa Macro F1. Đây là tiêu chí thử nghiệm, chưa phải tiêu chuẩn an toàn giao thông. Ngưỡng 0,75 thuộc bộ phân loại, độc lập với ngưỡng thời gian và lịch phát tải trong policy đã thống nhất. Đổi ngưỡng làm giảm cả báo nhầm và recall; không được chỉ báo cáo mặt có lợi.

Phiên bản ứng viên: `rf-nthu-lowfa-20261108-a035d671`, SHA256 `a46e09221e8159235a3628f44aab73ddffb266b54ada5e9b24d324bb03fe7e15`. Artifact riêng ở `edge-ai/ml-runs/nthu-camera-review-20261108/low-false-alarm/selected.joblib`. Kiểm tra `main.py --check` đã nạp đúng schema/thư viện; chưa thay artifact đối chiếu trong `run-submission.ps1`.

## Những gì dữ liệu cho thấy

- EAR trung vị khi mở mắt khoảng 0,301; EAR mean này nằm trong khoảng thường thấy của lớp âm development. Chưa có bằng chứng rằng EAR luôn bị đo thành mắt nhắm.
- Dao động EAR trong phiên camera thấp hơn phần lớn cửa sổ lớp âm development. EAR std trung vị khoảng 0,015, so với trung vị development âm khoảng 0,067; các cửa sổ camera được xét đều thấp hơn percentile 5 của chỉ số này.
- Yaw mean của camera khác nhiều lớp âm development; các đặc trưng hướng đầu có đóng góp trong một dự đoán báo nhầm được phân tích. Tuy nhiên bỏ hướng đầu không khắc phục được lỗi, như kết quả RF/SVM chỉ mắt cho thấy.
- Development có 4.264/5.551 cửa sổ dương. Cấu trúc nhãn, góc camera, điều kiện quay và vùng đặc trưng ít đại diện là các yếu tố cần khảo sát; chưa thể khẳng định một yếu tố duy nhất là nguyên nhân.

## Bước nghiệm thu tiếp theo

1. Giữ RF cũ và kết quả CV làm mốc; thử ứng viên giảm báo nhầm bằng cấu hình riêng, không ghi đè `.env` hay script bản đối chiếu.
2. Quan sát tại bàn: nhìn thẳng/chớp mắt tự nhiên → nhắm mắt mô phỏng → mở mắt hồi phục → quay đầu → mất mặt. Ghi mốc bắt đầu/kết thúc từng thao tác, model version và âm thanh thực nghe được. Nhắm mắt mô phỏng kiểm tra chức năng; không coi đó là bộ nhãn buồn ngủ tự nhiên đã được xác thực.
3. Đánh giá đồng thời báo nhầm, bỏ sót và thời gian phát hiện/hồi phục. Không chốt ứng viên chỉ vì sửa được ca mở mắt. Nếu đã dùng một phiên để chỉnh model thì dành phiên/người khác để kiểm tra sau khi khóa lại.
4. Nếu vẫn lỗi, bổ sung dữ liệu RGB cùng điều kiện triển khai với nhãn/nguồn rõ. Các phiên cá nhân dùng để train phải tách khỏi phiên nghiệm thu; tránh cửa sổ cùng video hoặc cùng người lọt sang test.

Ảnh mặt, video, log đặc trưng, dataset và joblib được giữ riêng ngoài Git. Repository chỉ lưu tổng hợp kết quả và công cụ chẩn đoán; chưa có xác nhận loa thật hay tải ESP32 thật đã đạt.

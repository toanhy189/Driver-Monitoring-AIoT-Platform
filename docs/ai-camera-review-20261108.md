# Chẩn đoán báo DROWSY khi mở mắt — 08/11/2026

## Kết luận hiện tại

**RF đối chiếu chưa đạt ca camera thật.** Người dùng xác nhận mở mắt, nhìn thẳng nhưng vẫn thấy DROWSY sau hơn 30 giây. Log suy luận có các cửa sổ PERCLOS = 0, thời gian nhắm mắt dài nhất = 0 nhưng RF vẫn vượt ngưỡng 0,4. Không thể giải thích ca này chỉ bằng cửa sổ dữ liệu cũ.

Phiên chẩn đoán đầu đã được người dùng đóng. Chưa thay model mặc định, artifact bàn giao hay policy `driver-bench-20261107-v1`. Các ứng viên ở thư mục thử nghiệm riêng; không sửa BE/FE để che kết quả nhận biết.

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

## Lượt camera thử ứng viên và lỗi ghép trạng thái

Người dùng đồng ý thử ứng viên giảm báo nhầm và đã đóng camera sau lượt thử. Phản hồi: đeo kính khó chuyển từ ATTENTIVE sang DROWSY khi nhắm mắt; quay đầu thường thành UNKNOWN. Vì vậy **ứng viên vẫn chưa đạt nghiệm thu**, dù log có một số đoạn DROWSY và DISTRACTED.

Có cửa sổ ghi nhắm mắt liên tục khoảng 8 giây, PERCLOS khoảng 0,5 nhưng RF score chỉ khoảng 0,33. Số đo mắt đã nhận nhắm ở cửa sổ đó; RF vẫn có thể bỏ sót. Chưa có mốc thao tác đeo/tháo kính chính xác nên không quy mọi khác biệt cho kính hay công bố recall theo điều kiện kính.

Ngoài mất mặt, code có một điều kiện cản quy tắc hướng đầu: `fuse_state(None, pose_status)` trả UNKNOWN trước khi xét hướng đầu đang quan sát hợp lệ. Đã sửa để trả DISTRACTED khi tracker hiện tại hợp lệ, đã hiệu chuẩn và đã xác nhận lệch đầu đủ thời gian, dù cửa sổ drowsiness chưa đủ. Không có bằng chứng hướng đầu đó thì vẫn UNKNOWN. DROWSY từ model vẫn giữ ưu tiên; policy 3/6/10 giây không thay đổi.

Bộ test AI sau sửa ghép trạng thái: **94/94 đạt**. Ca tracker không hợp lệ, đang hiệu chuẩn, chưa lệch đủ và mất pose vẫn kiểm tra UNKNOWN. Phần sửa này cần thử lại camera; không cam kết rằng quay đầu đến góc mất landmark sẽ luôn được nhận DISTRACTED.

## Bản kết hợp đang thử theo chấp thuận của TV3

TV3 đã đồng ý triển khai và thử RF kết hợp quy tắc nhắm mắt, vẫn giữ policy cảnh báo. Tùy chọn `AI_EYE_CLOSURE_GUARD_ENABLED=true` áp dụng khi đang chạy ML; mặc định `false` để các lượt chạy khác giữ cấu hình cũ.

- EAR vẫn dùng ngưỡng 0,20 hiện có; không sửa cách tạo feature đầu vào RF. Nếu landmark không đo được nhắm mắt thì quy tắc này cũng không giải quyết được.
- Nhắm mắt đo được liên tục ≥ 1 giây tạo thêm tín hiệu nguy cơ DROWSY, kể cả RF bỏ sót hoặc chưa đủ cửa sổ. Chớp mắt ngắn rời nhau không cộng dồn.
- Mở mắt liên tục ≥ 1 giây xóa tín hiệu quy tắc. Điều này không ép ATTENTIVE nếu RF vẫn báo DROWSY hoặc đầu còn lệch.
- Thiếu EAR, mất mặt hoặc gap > 0,5 giây xóa ngay bộ đếm và tín hiệu quy tắc. Không phát bù từ thời gian không quan sát được.
- Hướng đầu hiện tại hợp lệ, đã hiệu chuẩn và lệch đủ thời gian vẫn có thể tạo DISTRACTED khi RF chưa sẵn sàng. Không có bằng chứng mắt hay đầu đó thì UNKNOWN.
- Tín hiệu kết hợp tiếp tục qua xác nhận trạng thái và policy 3/6/10 giây, không gửi lệnh tải trực tiếp từ quy tắc mắt. Thời gian nhắm mắt, thời gian xác nhận, ngưỡng policy và thời gian thực thi là các giai đoạn khác nhau.

Log/overlay ghi rõ eye guard đang bật và có kích hoạt hay không. Debug quan sát thêm trạng thái thô, trạng thái xác nhận, pose, khoảng thời gian giữa frame và lý do chất lượng của lần snapshot RF gần nhất. Không đổi payload hay logic BE/FE cho việc thử này.

Các ngưỡng mắt là tham số thử nghiệm đã được TV3 đồng ý thử, chưa được kiểm chứng cho sử dụng ngoài thực tế. Nhắm mắt kéo dài là dấu hiệu đo được, không phải chẩn đoán buồn ngủ tự nhiên. **Chưa nghiệm thu bản kết hợp trên camera, chưa chốt làm model mặc định.**

Bộ test sau bổ sung quy tắc mắt đạt **101/101**, gồm 7 ca mới về nhắm liên tục, chớp mắt rời nhau, hồi phục, mất dữ liệu và ghép với RF. Đây là kiểm thử cơ chế bằng dữ liệu tổng hợp, không phải độ chính xác nhận biết.

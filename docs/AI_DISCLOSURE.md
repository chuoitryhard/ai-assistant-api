# Khai báo sử dụng AI

ChatGPT Work/Codex hỗ trợ phân tích tài liệu yêu cầu, tạo phần lớn mã nguồn và bộ hồ sơ, viết tests, chạy công cụ và sửa lỗi. Các file tỷ trọng AI cao gồm `app/*.py`, frontend trong `app/static`, tests, scripts, lab và các bản báo cáo. Đây là khai báo của bộ bàn giao, không chứng minh sinh viên đã tự thực hiện từng thao tác.

## Sai sót đã thực sự phát hiện

### Bỏ sót giới hạn khối token đầu tiên

Yêu cầu dẫn tới phần code: xây dựng streaming gateway có giới hạn đầu ra. Phiên bản AI tạo đầu tiên chỉ kiểm tra kích thước các token tiếp theo, bỏ qua token lấy trước để kiểm tra upstream. Khi viết test `test_oversized_first_chunk_rejected`, provider trả khối đầu 60.001 ký tự và API trả 200 dù giới hạn là 60.000. Test thật thất bại `assert 200 == 502`.

Sửa trong `app/main.py`, ngay sau `first = await anext(stream, "")`: kiểm tra `len(first)` và raise `AppError(502, "output_limit", ...)`. Khi lỗi xảy ra, đóng generator và giảm bộ đếm stream. Test hồi quy đã pass. Minh chứng: `docs/evidence/first-chunk-before-fix.txt`, XML trước sửa và `test-results.xml` sau sửa. Không có dữ liệu bí mật trong fixture.

### Script khởi động không tìm được package app

Yêu cầu dẫn tới phần code: cung cấp script chạy server đơn giản. Phiên bản đầu chạy Uvicorn bằng import string `app.main:app`, nhưng thực thi `python scripts/serve.py` khi source chưa được cài editable chỉ thêm thư mục scripts vào import path. Lệnh thật thất bại `ModuleNotFoundError: No module named 'app'`.

Sửa bằng đưa đường dẫn project root suy ra từ `__file__` vào `sys.path`, không dùng đường dẫn tuyệt đối của máy tạo. Kiểm chứng lại bằng `scripts/verify_runtime.py`, start server, HTTP smoke và export OpenAPI thành công. Minh chứng trước sửa: `docs/evidence/serve-before-fix.txt`; sau sửa: `runtime.log` và `http-smoke.json`.

Hai mục trên là lỗi đã quan sát trong quá trình xây dựng. Khi nhóm bổ sung trải nghiệm dùng AI, giữ nguyên prompt và kết quả thực tế, không tạo thêm tình huống lỗi giả để đủ mục chấm.

## Kiểm chứng và mức độ tự chủ

Đã chạy pytest, Ruff, HTTP qua TCP, so sánh framework và kiểm tra bố cục hồ sơ. LLM thật, triển khai Docker trên máy đích, lịch sử commit nhóm và chấm chéo lab cần nhóm thực hiện tiếp. Không tuyên bố sinh viên có thể tự viết phần nào khi chưa có minh chứng. Mỗi thành viên tự chạy lại các tests và giải thích Pydantic, dependency graph, lifecycle, async I/O và việc đóng upstream stream.

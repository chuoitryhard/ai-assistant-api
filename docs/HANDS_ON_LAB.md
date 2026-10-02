# Hands-on lab 40 phút

## Chủ đề

Xây dựng endpoint SSE dùng Pydantic, Depends và async I/O, rồi kiểm chứng schema sai và dependency override. Người học phải phân biệt await chờ I/O với blocking code, tạo khung SSE hợp lệ và giải thích lỗi trước/sau khi gửi HTTP header. Bài này vượt phần cài đặt Hello World hoặc CRUD cơ bản.

## Chuẩn bị

Python 3.11/3.12, terminal, trình soạn thảo, `curl` hoặc Swagger. Từ repo cài `python -m pip install -e '.[dev]'`. Dùng `labs/starter.py` làm điểm bắt đầu. Đáp án ở `labs/solution.py`. Không cần tài khoản AI hoặc gọi LLM.

## Các bước

1. **0–5 phút:** mở starter, chạy `uvicorn labs.starter:app --port 8010`. Xem schema Prompt trong `/docs`. Gửi câu hỏi và quan sát đầu ra chưa có cấu trúc event/data.
2. **5–12 phút:** thêm `model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)` vào Prompt. Gửi `{"question":" "}` và `{"question":"hi","extra":1}`. Kỳ vọng 422. Giải thích strip chạy trước min_length và không âm thầm bỏ trường lạ.
3. **12–22 phút:** trong generator thêm `await asyncio.sleep(settings['delay'])`. Đây là chờ timer mô phỏng, không blocking event loop. Với hệ thống thật, await HTTPX chờ dữ liệu mạng. Tạo `event: token\ndata: {JSON}\n\n`. Cuối generator thêm `event: done`.
4. **22–28 phút:** chạy `curl -N -H 'Content-Type: application/json' -d '{"question":"hello FastAPI streaming"}' http://127.0.0.1:8010/stream`. Quan sát nhiều event. Giải thích `-N` tắt buffering phía curl. Không dùng thời gian TestClient để kết luận token được truyền ngay qua TCP.
5. **28–36 phút:** viết test dùng `app.dependency_overrides[config] = lambda: {'delay': 0}`. Kiểm tra số token và done; xóa override ở finally. Chạy đáp án với `pytest -q labs/test_solution.py`.
6. **36–40 phút:** giải thích dependency graph `route → config`, vai trò Pydantic và vì sao không gọi `time.sleep` trực tiếp trong async generator. Thay đổi max_length và kiểm tra OpenAPI phản ánh thay đổi.

## Ba bài tập và đáp án

**Bài 1:** giới hạn question 120 ký tự và chặn extra. Đáp án: Field min/max_length, ConfigDict strip + forbid. Test: trắng/121 ký tự/trường lạ nhận 422, chuỗi ngắn hợp lệ nhận 200.

**Bài 2:** phát mỗi từ thành một SSE token và kết thúc bằng done. Đáp án ở solution.events; event được phân tách bằng hai newline và JSON được encode để newline trong dữ liệu không làm vỡ khung.

**Bài 3:** bỏ delay trong test bằng dependency override thay vì sửa production config. Đáp án ở `labs/test_solution.py`. Override phải được dọn để không ảnh hưởng test sau.

## Lỗi đã gặp trong sản phẩm và cách tránh

- Khối đầu được lấy trước để kiểm tra upstream nhưng không qua limit: kiểm tra ngay sau anext, giữ test hồi quy.
- Chạy `python scripts/serve.py` không tìm app: dùng project root hoặc cài package editable, không hardcode đường dẫn máy.
- Quan sát response đầy đủ trong TestClient không chứng minh stream bị buffer: cần phép thử qua TCP; bộ repo có verify_runtime.py.

## Chấm chéo

Nhóm khác làm bài không dùng AI trong phần đánh giá tại chỗ. Ghi người thử, thời gian, lỗi họ gặp, kết quả ba bài tập và sửa lab nếu hướng dẫn thiếu. Không khai đã chấm chéo khi chưa có người thử. Các trường này được để trống trong hồ sơ để ghi kết quả thật.

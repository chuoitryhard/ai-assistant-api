# Kịch bản demo và bảo vệ

## Demo 3 phút

0:00–0:20 giới thiệu bài toán và FastAPI là công nghệ chính. 0:20–0:40 mở `/docs`, chỉ schema ChatRequest và security dependency. 0:40–1:10 upload `samples/lesson.pdf`, theo dõi 202 và ready. 1:10–1:50 chọn tài liệu, hỏi về async và quan sát SSE; nói rõ provider demo hay LLM thật. 1:50–2:10 mở nguồn trích đoạn. 2:10–2:35 gửi payload sai từ Swagger để thấy 422. 2:35–3:00 chạy test hoặc mở evidence, chỉ giới hạn và hướng phát triển.

Video 2–3 phút là khuyến khích trong yêu cầu môn. Bộ bàn giao có kịch bản để nhóm tự quay với người trình bày và máy triển khai thực tế; chưa có video của nhóm.

## Câu hỏi tại chỗ

1. Endpoint nào async? Upload chờ file I/O; chat chờ mạng HTTPX; store chờ thread chạy SQLite. Parser là synchronous trong process pool. Dependency lấy config/auth không cần await.
2. Dependency tạo ở đâu? Lifespan tạo resources vào app.state; get_store/get_provider trả resources dùng lại; require_owner dùng get_settings và APIKeyHeader. FastAPI resolve cây dependency theo request.
3. Input sai kiểu lỗi ở tầng nào? Pydantic trước khi hàm route chạy; handler đổi lỗi thành error contract HTTP 422.
4. Lỗi sau HTTP 200 làm sao? SSE error, không đổi HTTP status đã gửi, frontend không coi là done.
5. Worker khác BackgroundTasks thế nào? Có trạng thái job lưu SQLite, claim, recovery restart; BackgroundTasks không cung cấp durable queue.
6. Thêm limit max_tokens? Sửa Field trong schema, xem OpenAPI và chạy validation test.
7. Tại sao không dùng nhiều Uvicorn workers? Startup recovery và stream count hiện dựa mô hình một process, cần kiến trúc worker riêng để mở rộng.

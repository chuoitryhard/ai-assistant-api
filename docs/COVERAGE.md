# Ma trận phủ yêu cầu

| Yêu cầu | Tầng | Vị trí trong sản phẩm | Kiểm chứng |
|---|---|---|---|
| Pydantic request/response | T1 lõi | schemas, ChatOut, DocumentOut | test_validation, OpenAPI |
| Depends dùng chung | T1 lõi | dependencies, require_owner, store/provider | dependency override |
| Async đúng chỗ | T1 lõi | provider HTTPX, SQLite to_thread, ProcessPool | tests và TCP smoke |
| HTTP status/lỗi | T1 lõi | AppError và exception handlers | các test lỗi |
| OpenAPI/response models | T1 chọn thêm | router và schemas | docs/openapi.json |
| Exception handler tập trung | T1 chọn thêm | main | error contract |
| Lifespan | T1 chọn thêm | create_app lifespan | worker/client shutdown |
| Middleware log | T1 chọn thêm | RequestLogMiddleware | runtime.log |
| TestClient và override | T1 chọn thêm | tests | test-results.xml |
| Repo chuẩn, cấu hình, CI | Chuẩn repo áp dụng | pyproject, .env.example, Dockerfile, CI | Ruff/pytest đã chạy; CI cloud và Docker chưa chạy |
| Streaming SSE và async provider | Kỹ thuật sâu của sản phẩm | provider và chat_stream | fake upstream và TCP demo |
| Durable worker một tiến trình | Kỹ thuật sâu của sản phẩm | store/extraction | restart recovery test |

Tầng 2/Tầng 3 trong tài liệu gốc tham chiếu Phần D/C của Danh mục công nghệ chưa được đính kèm. Bảng này khai những kỹ thuật thực sự có; nhóm cần đối chiếu thêm danh mục đầy đủ trước khi gán mã tầng chính thức. Không khai BackgroundTasks, embedding, agent, OCR, JWT hoặc multi-replica.

Thí nghiệm độc lập `compare_frameworks.py` nằm ngoài sản phẩm, không đưa vào bảng để tăng độ phức tạp. Bảng phủ cuối phải khóa cùng commit source trước bảo vệ ít nhất 24 giờ. Kèm hash ở biên bản niêm phong của nhóm.

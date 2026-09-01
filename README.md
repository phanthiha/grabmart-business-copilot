# GrabMart Assortment & Operations Copilot

Ứng dụng Streamlit hỗ trợ chủ cửa hàng phân tích dữ liệu GrabMart đã chuẩn hóa trên BigQuery.

## Chức năng

- Dashboard doanh số, giao dịch và giờ cao điểm.
- Ma trận ABC–XYZ và danh sách sản phẩm cần ưu tiên rà soát.
- Kiểm toán trùng tên, mô tả, ảnh, SKU và barcode.
- Phân tích MIWI Missing/Wrong và Customer Review.
- Trung tâm hành động có căn cứ dữ liệu, khu vực thao tác, trạng thái xử lý và tệp CSV bàn giao.
- Liên kết mở GrabMerchant chính thức để chủ cửa hàng đăng nhập, xác minh và tự duyệt thay đổi.

Ứng dụng không đăng nhập tự động, không thu thập dữ liệu bằng scraping và không tự động thay đổi thông tin trên GrabMerchant.

Luồng vận hành: `BigQuery → phân tích trên Streamlit → xác minh của chủ cửa hàng → thao tác trên GrabMerchant → đo lường kỳ tiếp theo`.

## Chạy cục bộ

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Nếu chưa cấu hình BigQuery, ứng dụng tự chuyển sang dữ liệu demo tổng hợp.

## Kết nối BigQuery

1. Sao chép `.streamlit/secrets.example.toml` thành `.streamlit/secrets.toml`.
2. Điền thông tin service account có quyền đọc dataset.
3. Không commit `secrets.toml` hoặc khóa JSON lên GitHub.

Dataset mặc định:

```text
plasma-renderer-507213-p8.grabmart_business
```

## Triển khai Streamlit Community Cloud

1. Đưa mã nguồn lên GitHub.
2. Mở `https://share.streamlit.io` và chọn **Create app**.
3. Chọn repository, branch `main` và `streamlit_app.py`.
4. Dán secrets vào **Advanced settings → Secrets**.
5. Chọn **Deploy**.

## Bảo mật dữ liệu

- Không đưa CSV kinh doanh hoặc đánh giá khách hàng lên repository công khai.
- Không lưu tên khách hàng, Order ID hoặc mật khẩu Grab trong mã nguồn.
- Chỉ cấp cho service account quyền đọc các bảng cần thiết.
- Nên triển khai ứng dụng ở chế độ private khi dùng dữ liệu thật.

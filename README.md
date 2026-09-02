# GrabMart Assortment & Operations Copilot

Ứng dụng Streamlit hỗ trợ chủ cửa hàng phân tích dữ liệu GrabMart đã chuẩn hóa trên BigQuery.

## Chức năng

- Dashboard doanh số, giao dịch và giờ cao điểm.
- Ma trận ABC–XYZ và danh sách sản phẩm cần ưu tiên rà soát.
- Kiểm toán trùng tên, mô tả, ảnh, SKU và barcode.
- Nhận gói ZIP thực đơn mới nhất từ GrabMerchant, xuất phiếu xử lý CSV, kiểm tra thay đổi và tạo lại ZIP đúng cấu trúc để cập nhật hàng loạt.
- Phân tích MIWI Missing/Wrong và Customer Review.
- Khám phá tám bảng dữ liệu đã giới hạn cột: xem kích thước, cấu trúc, tỷ lệ thiếu, tìm kiếm và tải dữ liệu phân tích đã khử trường nhạy cảm.
- Phân tích thực nghiệm trên tám bảng dữ liệu: tập trung doanh thu, tần suất, ABC–XYZ, hiệu suất nhóm/giá, chất lượng dữ liệu, khuyến mãi, Chi-square/Cramér’s V, hồi quy logistic cross-validation và phân tích độ nhạy.
- Trung tâm hành động có căn cứ dữ liệu, khu vực thao tác, trạng thái xử lý và tệp CSV bàn giao.
- Liên kết mở GrabMerchant chính thức để chủ cửa hàng đăng nhập, xác minh và tự duyệt thay đổi.

Ứng dụng không đăng nhập tự động, không thu thập dữ liệu bằng scraping và không tự động thay đổi thông tin trên GrabMerchant.

Liên kết trải nghiệm cửa hàng trên GrabMart: `https://r.grab.com/o/NbQzAJVn`.

Luồng vận hành: `BigQuery → phân tích trên Streamlit → xác minh của chủ cửa hàng → thao tác trên GrabMerchant → đo lường kỳ tiếp theo`.

## Chạy cục bộ

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Ứng dụng công khai mặc định dùng dữ liệu demo tổng hợp. Dữ liệu thật chỉ được bật khi người dùng đăng nhập Google bằng email nằm trong `allowed_emails` và quản trị viên đặt `enable_live_data=true` trong Streamlit Secrets; truy vấn vẫn chỉ đọc danh sách cột an toàn trong `src/data.py`.

## Kết nối BigQuery

1. Sao chép `.streamlit/secrets.example.toml` thành `.streamlit/secrets.toml`.
2. Điền thông tin service account có quyền đọc dataset.
3. Không commit `secrets.toml` hoặc khóa JSON lên GitHub.
4. Tạo Google OAuth Web Client và khai báo redirect URI `https://grabmart-business-copilot.streamlit.app/oauth2callback`.
5. Điền `[auth]`, `allowed_emails` và đặt `enable_live_data=true` trong Streamlit Secrets. Không đưa OAuth secret hoặc danh sách email được phép lên GitHub.
6. Chỉ cấp tài khoản dịch vụ quyền BigQuery Job User và Data Viewer trên dataset/view an toàn; không cấp Owner/Admin.

Luồng truy cập: khách công khai chỉ thấy demo → người dùng đăng nhập Google → ứng dụng đối chiếu email với allowlist riêng tư → tài khoản hợp lệ mới có thể chuyển sang dữ liệu BigQuery thật → đăng xuất để kết thúc phiên.

Các trường `customer`, `review`, `reply`, `store_id`, `merchant`, `order_id` và `short_order_number` không được truy vấn hoặc tải xuống từ ứng dụng.

Dataset mặc định:

```text
plasma-renderer-507213-p8.grabmart_business
```

## Notebook kiểm chứng kết quả

Notebook [`notebooks/BigData_GrabMart_Reproducible_Analysis.ipynb`](notebooks/BigData_GrabMart_Reproducible_Analysis.ipynb) thực hiện tuần tự:

1. Xác thực tài khoản Google trên Colab.
2. Đọc tám bảng từ BigQuery.
3. Tính KPI, Gini, ABC–XYZ, hiệu quả nhóm và giá.
4. Chạy Chi-square và Cramér's V trực tiếp từ dữ liệu.
5. Chạy hồi quy logistic cross-validation 5-fold.
6. Sinh các bảng, biểu đồ và xuất bảng đối chiếu ra CSV.

[Mở notebook trực tiếp trên Google Colab](https://colab.research.google.com/github/phanthiha/grabmart-business-copilot/blob/main/notebooks/BigData_GrabMart_Reproducible_Analysis.ipynb)

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

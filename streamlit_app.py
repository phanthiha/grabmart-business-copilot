from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.grab_catalogue import (
    apply_review,
    build_grab_zip,
    catalogue_audit as audit_grab_package,
    make_review_sheet,
    read_grab_zip,
    read_review_csv,
    validate_review,
)
from src.data import load_data
from src.clipboard_image import decode_pasted_image, paste_image_zone
from src.metrics import action_list, catalogue_issues, gini
from src.menu_sales import combine_menu_sales, period_comparison, preparation_board, price_changes, product_performance
from src.supplier_products import (
    INITIAL_UPLOADED_PRODUCTS,
    build_create_items_zip,
    recalculate_prices,
    safe_image_filename,
    supplier_product_table,
)
from src.paper_experiments import (
    assortment_performance,
    concentration,
    cramer_test,
    duplicate_test,
    frequency_bands,
    logistic_cross_validation,
    operational_extension,
    promotion_summary,
    quality_summary,
    sensitivity,
)


st.set_page_config(page_title="GrabMart Business Copilot", page_icon="🛒", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.7rem; padding-bottom: 3rem;}
[data-testid="stMetric"] {background:#fff; border:1px solid #dce9e1; border-radius:14px; padding:14px;}
.hero {background:linear-gradient(120deg,#003d29,#00b14f); color:white; padding:24px 28px; border-radius:18px; margin-bottom:18px;}
.hero h1 {margin:0 0 6px 0; font-size:2rem;}
.hero p {margin:0; opacity:.92;}
.workflow {background:#f3faf6; border-left:5px solid #00b14f; padding:14px 18px; border-radius:10px; margin:8px 0 18px;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>GrabMart Assortment & Operations Copilot</h1>
  <p>Hỗ trợ chủ cửa hàng đánh giá danh mục, chất lượng vận hành và tiếng nói khách hàng bằng BigQuery.</p>
</div>
""", unsafe_allow_html=True)

shop_intro, shop_action = st.columns([2.4, 1])
with shop_intro:
    st.markdown("**Trải nghiệm cửa hàng thực tế trên GrabMart**")
    st.caption("Tham khảo danh mục sản phẩm đang phục vụ khách hàng trên ứng dụng Grab.")
with shop_action:
    st.link_button("🛍️ Xem cửa hàng trên GrabMart ↗", "https://r.grab.com/o/NbQzAJVn", width="stretch")

with st.expander("Giới thiệu dự án và quy trình thực hiện", expanded=True):
    st.markdown("""
Ứng dụng sử dụng **dữ liệu kinh doanh thực tế được xuất từ GrabMerchant** để hỗ trợ chủ cửa hàng phát hiện vấn đề và đưa ra quyết định dựa trên dữ liệu.

**Quy trình thực hiện:**

1. Thu thập, làm sạch và chuẩn hóa dữ liệu kinh doanh.
2. Lưu trữ dữ liệu thành tám bảng trên **Google BigQuery**.
3. Kết nối Streamlit với BigQuery bằng tài khoản dịch vụ chỉ có quyền đọc.
4. Phân tích doanh số, giờ cao điểm, danh mục ABC–XYZ, chất lượng catalogue, khuyến mãi, MIWI và đánh giá khách hàng.
5. Tạo danh sách công việc ưu tiên kèm căn cứ dữ liệu để chủ cửa hàng xác minh.
6. Chủ cửa hàng đăng nhập **GrabMerchant chính thức** để thực hiện quyết định và theo dõi kết quả ở kỳ tiếp theo.

Ứng dụng **không lưu mật khẩu Grab và không tự động thay đổi dữ liệu**; đây là công cụ hỗ trợ ra quyết định, còn quyết định cuối cùng thuộc về chủ cửa hàng.
""")

with st.sidebar:
    st.header("Điều khiển")
    try:
        live_enabled_by_admin = bool(st.secrets.get("enable_live_data", False))
        allowed_emails = {
            str(email).strip().lower()
            for email in st.secrets.get("allowed_emails", [])
        }
        auth_configured = bool(st.secrets.get("auth"))
    except (FileNotFoundError, RuntimeError):
        live_enabled_by_admin = False
        allowed_emails = set()
        auth_configured = False

    logged_in = bool(auth_configured and st.user.is_logged_in)
    user_email = str(st.user.get("email", "")).strip().lower() if logged_in else ""
    authorized = bool(logged_in and user_email in allowed_emails)
    live_enabled = bool(live_enabled_by_admin and authorized)

    st.markdown("**Quyền truy cập dữ liệu thật**")
    if not auth_configured:
        st.caption("🔒 Chưa cấu hình Google OAuth; chỉ dùng dữ liệu demo.")
    elif not logged_in:
        st.button("Đăng nhập bằng Google", on_click=st.login, width="stretch")
        st.caption("Đăng nhập chỉ dùng để xác minh quyền xem dữ liệu BigQuery.")
    elif authorized:
        st.success(f"Đã xác thực: {user_email}")
        st.button("Đăng xuất", on_click=st.logout, width="stretch")
    else:
        st.error("Tài khoản này không được cấp quyền xem dữ liệu thật.")
        st.button("Đăng xuất", on_click=st.logout, width="stretch")

    use_demo = st.toggle(
        "Dùng dữ liệu demo an toàn",
        # Khách công khai luôn ở demo; tài khoản đã xác thực mặc định vào dữ liệu thật.
        value=not live_enabled,
        disabled=not live_enabled,
        help=(
            "Chỉ có thể tắt sau khi đăng nhập bằng tài khoản được cho phép và "
            "quản trị viên đã bật enable_live_data trong Streamlit Secrets."
        ),
    )
    if not live_enabled:
        st.caption("🔒 Dữ liệu thật đang bị khóa.")
    elif use_demo:
        st.caption("🧪 Đang xem dữ liệu demo; tắt công tắc để dùng BigQuery thật.")
    else:
        st.caption("✅ Đang sử dụng dữ liệu BigQuery thật đã giới hạn cột.")
    page = st.radio("Chức năng", [
        "Tổng quan kinh doanh",
        "Danh mục ABC–XYZ",
        "Kiểm toán catalogue",
        "Phân tích Menu Sales",
        "Tạo sản phẩm hàng loạt",
        "MIWI & đánh giá khách hàng",
        "Phân tích thực nghiệm",
        "Khám phá bảng dữ liệu",
        "Danh sách công việc",
    ])
    st.divider()
    st.markdown("**Thực hiện quyết định**")
    st.caption("Ứng dụng phân tích dữ liệu; GrabMerchant là nơi xác nhận và thực hiện thay đổi.")
    st.link_button("Mở GrabMerchant chính thức ↗", "https://merchant.grab.com/", width="stretch")

# Truyền một đối số để tương thích cả khi Streamlit Cloud còn cache phiên bản
# cũ của mô-đun src.data trong lúc rolling deploy. Cờ bảo vệ được hợp nhất ở đây.
bundle = load_data(use_demo or not live_enabled)
sales = bundle["sales_daily"].copy()
score = bundle["product_scoring"].copy()
reviews = bundle["customer_reviews"].copy()
miwi = bundle["miwi_item_breakdown"].copy()
miwi_events = bundle["miwi_heatmap"].copy()
peak = bundle["peak_hours"].copy()
offers = bundle["offers"].copy()

st.caption(f"Nguồn hiện tại: {bundle.source}")

if "date" in sales:
    sales["date"] = pd.to_datetime(sales["date"])
    min_date, max_date = sales.date.min().date(), sales.date.max().date()
    selected = st.sidebar.date_input("Khoảng thời gian", (min_date, max_date), min_value=min_date, max_value=max_date)
    if isinstance(selected, tuple) and len(selected) == 2:
        start, end = pd.Timestamp(selected[0]), pd.Timestamp(selected[1])
        sales = sales[sales.date.between(start, end)]


def money(value: float) -> str:
    return f"{value:,.0f} ₫"


@st.cache_data(show_spinner="Đang chạy hồi quy logistic 5-fold...")
def cached_logistic_cv(frame: pd.DataFrame) -> pd.DataFrame:
    return logistic_cross_validation(frame)


if page == "Tổng quan kinh doanh":
    st.header("Tổng quan kinh doanh")
    gross = float(sales.gross_sales_vnd.sum())
    net = float(sales.net_sales_vnd.sum())
    tx = int(sales.transaction_count.sum())
    sold = int(score.recorded_sales.sum())
    cols = st.columns(5)
    cols[0].metric("Doanh số gộp", money(gross))
    cols[1].metric("Doanh số thuần", money(net))
    cols[2].metric("Giao dịch", f"{tx:,}")
    cols[3].metric("Giá trị đơn TB", money(gross / tx if tx else 0))
    cols[4].metric("Sản phẩm có bán", f"{sold}/{len(score)}")

    left, right = st.columns([1.7, 1])
    daily = sales.groupby("date", as_index=False).agg(gross_sales_vnd=("gross_sales_vnd", "sum"), transaction_count=("transaction_count", "sum"))
    left.plotly_chart(px.line(daily, x="date", y="gross_sales_vnd", title="Doanh số theo ngày", markers=True), width="stretch")
    hour = peak.groupby("hour", as_index=False).transaction_count.sum()
    right.plotly_chart(px.bar(hour, x="hour", y="transaction_count", title="Giao dịch theo giờ", color_discrete_sequence=["#00B14F"]), width="stretch")

    c1, c2, c3 = st.columns(3)
    c1.metric("Gini toàn danh mục", f"{gini(score.gross_revenue):.3f}")
    c2.metric("Chi phí khuyến mãi", money(float(offers.spend_vnd.sum())))
    c3.metric("Sự cố MIWI", f"{int(miwi.total_reported.sum()):,}")

elif page == "Danh mục ABC–XYZ":
    st.header("Phân tích danh mục ABC–XYZ")
    groups = ["Tất cả"] + sorted(score.product_group.dropna().unique().tolist())
    chosen_group = st.selectbox("Nhóm sản phẩm", groups)
    view = score if chosen_group == "Tất cả" else score[score.product_group.eq(chosen_group)]
    matrix = pd.crosstab(view.abc, view.xyz)
    left, right = st.columns([1, 1.4])
    left.plotly_chart(px.imshow(matrix, text_auto=True, color_continuous_scale="Greens", title="Ma trận ABC–XYZ"), width="stretch")
    priority = view.groupby("priority_label", as_index=False).agg(products=("product_name_current", "size"), revenue=("gross_revenue", "sum"))
    right.plotly_chart(px.bar(priority, x="products", y="priority_label", orientation="h", color="priority_label", title="Mức ưu tiên rà soát"), width="stretch")
    columns = ["product_name_current", "product_group", "price_segment", "gross_revenue", "units_sold", "selling_days", "abc", "xyz", "review_priority_score", "priority_label"]
    st.dataframe(view[columns].sort_values(["review_priority_score", "gross_revenue"], ascending=[False, True]), width="stretch", hide_index=True)
    st.download_button("Tải danh sách sản phẩm", view[columns].to_csv(index=False).encode("utf-8-sig"), "product_review.csv", "text/csv")
    st.info("Điểm ưu tiên là công cụ sàng lọc. Sản phẩm có điểm cao không đồng nghĩa phải tự động xóa khỏi GrabMart.")

elif page == "Kiểm toán catalogue":
    st.header("Kiểm toán chất lượng catalogue")
    analysis_tab, grab_tab = st.tabs(["Chỉ số phân tích", "Cập nhật hàng loạt GrabMerchant"])
    with analysis_tab:
        st.info("Cửa hàng soạn hoa theo hình ảnh và quy cách mẫu. SKU và barcode không bắt buộc, vì vậy thiếu hai trường này không được xem là lỗi catalogue.")
        issues = catalogue_issues(score)
        left, right = st.columns([1.2, 1])
        left.plotly_chart(px.bar(issues, x="Số sản phẩm", y="Vấn đề", orientation="h", color="Số sản phẩm", color_continuous_scale="Greens"), width="stretch")
        right.dataframe(issues, width="stretch", hide_index=True)
        st.caption("Các chỉ số này lấy từ bảng phân tích BigQuery. Để tạo ZIP cập nhật Grab, sử dụng thẻ bên cạnh.")

    with grab_tab:
        st.markdown("""
<div class="workflow"><b>Quy trình:</b> Tải ZIP thực đơn mới nhất từ GrabMerchant → kiểm toán → tải phiếu CSV → sửa và nhập lại → kiểm tra → tải ZIP cập nhật.</div>
""", unsafe_allow_html=True)
        if not authorized:
            st.warning("Vui lòng đăng nhập bằng tài khoản được cấp quyền để xử lý gói thực đơn thật.")
        else:
            menu_upload = st.file_uploader("1. Tải lên ZIP thực đơn mới nhất từ GrabMerchant", type=["zip"], key="grab_menu_zip")
            if menu_upload is not None:
                try:
                    package = read_grab_zip(menu_upload.getvalue())
                    products = package.products
                    summary, package_masks = audit_grab_package(products)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Sản phẩm", f"{len(products):,}")
                    c2.metric("Đang bán", f"{products['*AvailableStatus'].eq('AVAILABLE').sum():,}")
                    c3.metric("Danh mục", f"{products['*GrabCategoryName'].nunique():,}")
                    c4.metric("CSV nguồn", package.csv_name.split("_")[1] if "_" in package.csv_name else "Đã nhận")
                    st.success("ZIP hợp lệ; CSV, resources và images sẽ được bảo toàn khi xuất lại.")
                    st.info("Đối với hoa thiết kế, để trống SKU/barcode là hợp lệ. Ứng dụng chỉ cảnh báo barcode đã nhập nhưng không đúng cấu trúc GTIN để chủ cửa hàng xóa hoặc xác minh trên bao bì.")
                    st.dataframe(summary, width="stretch", hide_index=True)

                    issue_filter = st.selectbox("2. Chọn danh sách cần xử lý", summary["Vấn đề"], key="grab_issue")
                    mask = package_masks[issue_filter]
                    review_sheet = make_review_sheet(products, mask, issue_filter)
                    st.caption(f"Tìm thấy {len(review_sheet):,} sản phẩm. Action mặc định là REVIEW nên chưa làm thay đổi catalogue.")
                    st.dataframe(review_sheet.head(200), width="stretch", hide_index=True)
                    st.download_button(
                        "Tải phiếu xử lý CSV",
                        review_sheet.to_csv(index=False).encode("utf-8-sig"),
                        f"grab_review_{issue_filter.replace(' ', '_').lower()}.csv",
                        "text/csv",
                    )

                    direct_tab, csv_tab = st.tabs(["Sửa trực tiếp trên form", "Sửa bằng CSV"])
                    with direct_tab:
                        st.markdown("**3A. Chỉnh sửa các sản phẩm đã chọn**")
                        st.caption("Đổi Action sang UPDATE, HIDE hoặc DISCONTINUE. Các dòng REVIEW/KEEP sẽ không làm thay đổi thực đơn.")
                        reviewed_direct = st.data_editor(
                            review_sheet,
                            width="stretch",
                            hide_index=True,
                            disabled=[
                                "ItemID", "StoreID", "Issue", "DuplicateGroup",
                                "CurrentItemName", "CurrentPrice", "CurrentCategory",
                                "CurrentStatus", "CurrentDescription",
                                "CurrentBarcode", "CurrentSKU",
                            ],
                            column_config={
                                "Action": st.column_config.SelectboxColumn(
                                    "Hành động",
                                    options=["REVIEW", "KEEP", "UPDATE", "HIDE", "DISCONTINUE"],
                                    required=True,
                                    help="UPDATE: dùng các cột Proposed; HIDE: ẩn món; DISCONTINUE: ngừng bán vĩnh viễn.",
                                ),
                                "ItemID": st.column_config.TextColumn("Mã sản phẩm"),
                                "CurrentItemName": st.column_config.TextColumn("Tên hiện tại"),
                                "ProposedPrice": st.column_config.TextColumn(
                                    "Giá mới",
                                    help="Nhập số nguyên, ví dụ 269000; không nhập dấu chấm, ₫ hoặc chữ.",
                                ),
                                "ProposedStatus": st.column_config.SelectboxColumn(
                                    "Trạng thái mới",
                                    options=["AVAILABLE", "UNAVAILABLE_TODAY", "UNAVAILABLE_PERMANENTLY", "HIDDEN"],
                                ),
                                "ProposedItemName": st.column_config.TextColumn("Tên mới", max_chars=80),
                                "ProposedDescription": st.column_config.TextColumn("Mô tả mới", max_chars=300),
                                "ProposedBarcode": st.column_config.TextColumn(
                                    "Barcode mới",
                                    help="Hoa làm theo mẫu không cần barcode. Để trống cột này để xóa mã không phù hợp.",
                                ),
                                "ProposedSKU": st.column_config.TextColumn(
                                    "SKU mới",
                                    help="SKU không bắt buộc đối với cửa hàng soạn hoa theo hình mẫu.",
                                ),
                            },
                            key=f"grab_direct_editor_{issue_filter}",
                        )
                        direct_errors = validate_review(package, reviewed_direct)
                        direct_updated, direct_log = apply_review(package, reviewed_direct) if direct_errors.empty else (None, pd.DataFrame())
                        if not direct_errors.empty:
                            st.error(f"Form có {len(direct_errors):,} lỗi cần sửa.")
                            st.dataframe(direct_errors, width="stretch", hide_index=True)
                        elif direct_log.empty:
                            st.info("Chưa có thay đổi. Chọn Action phù hợp ở ít nhất một dòng.")
                        else:
                            st.markdown("**4A. Xem trước thay đổi từ form**")
                            st.dataframe(direct_log, width="stretch", hide_index=True)
                            direct_confirmed = st.checkbox(
                                f"Tôi xác nhận {len(direct_log):,} thay đổi trên form",
                                key=f"confirm_direct_{issue_filter}",
                            )
                            if direct_confirmed:
                                direct_zip = build_grab_zip(package, direct_updated)
                                stem = package.csv_name.rsplit(".", 1)[0]
                                st.download_button("Tải ZIP cập nhật từ form", direct_zip, f"{stem}_updated.zip", "application/zip", type="primary", key=f"direct_zip_{issue_filter}")
                                st.download_button("Tải nhật ký thay đổi từ form", direct_log.to_csv(index=False).encode("utf-8-sig"), f"{stem}_change_log.csv", "text/csv", key=f"direct_log_{issue_filter}")

                    with csv_tab:
                        st.markdown("**3B. Nhập lại phiếu đã sửa bằng Excel/Google Sheets**")
                        review_upload = st.file_uploader("Tải lên phiếu CSV sau khi sửa", type=["csv"], key="grab_review_csv")
                    if review_upload is not None:
                        try:
                            reviewed = read_review_csv(review_upload.getvalue())
                            validation_errors = validate_review(package, reviewed)
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            action_counts = reviewed["Action"].str.strip().str.upper().value_counts().rename_axis("Action").reset_index(name="Số dòng")
                            st.dataframe(action_counts, width="stretch", hide_index=True)
                            if not validation_errors.empty:
                                st.error(f"Phiếu xử lý có {len(validation_errors):,} lỗi. Hãy sửa và tải lại trước khi tạo ZIP.")
                                st.dataframe(validation_errors, width="stretch", hide_index=True)
                                st.download_button("Tải danh sách lỗi", validation_errors.to_csv(index=False).encode("utf-8-sig"), "grab_review_errors.csv", "text/csv")
                            else:
                                updated_catalogue, change_log = apply_review(package, reviewed)
                                st.success("Phiếu xử lý hợp lệ.")
                                if change_log.empty:
                                    st.info("Chưa có thay đổi để xuất. Hãy đặt Action là UPDATE, HIDE hoặc DISCONTINUE cho sản phẩm cần xử lý.")
                                else:
                                    st.markdown("**4. Xem trước thay đổi**")
                                    st.dataframe(change_log, width="stretch", hide_index=True)
                                    confirmed = st.checkbox(
                                        f"Tôi đã kiểm tra {len(change_log):,} thay đổi và muốn tạo ZIP cập nhật GrabMerchant",
                                        key="confirm_grab_zip",
                                    )
                                    if confirmed:
                                        updated_zip = build_grab_zip(package, updated_catalogue)
                                        stem = package.csv_name.rsplit(".", 1)[0]
                                        st.download_button("Tải ZIP cập nhật GrabMerchant", updated_zip, f"{stem}_updated.zip", "application/zip", type="primary")
                                        st.download_button("Tải nhật ký thay đổi", change_log.to_csv(index=False).encode("utf-8-sig"), f"{stem}_change_log.csv", "text/csv")
                                        st.info("Tải ZIP lên GrabMerchant tại Thực đơn → Cập nhật hàng loạt → Chỉnh sửa món hàng loạt. Chỉ nhấn Áp dụng sau khi Grab kiểm tra thành công.")

elif page == "Phân tích Menu Sales":
    st.header("Phân tích Menu Sales và chuẩn bị hoa theo mẫu")
    st.caption("Tải một hoặc nhiều báo cáo Menu Sales. Ứng dụng tự nhận diện tiêu đề Việt/Anh, phát hiện chồng lặp và không cộng trùng dữ liệu.")
    if not authorized:
        st.warning("Vui lòng đăng nhập bằng tài khoản được cấp quyền để phân tích file kinh doanh thật.")
    else:
        sales_uploads = st.file_uploader("Tải các file Menu Sales CSV", type=["csv"], accept_multiple_files=True, key="menu_sales_uploads")
        if sales_uploads:
            try:
                menu_result = combine_menu_sales([(file.name, file.getvalue()) for file in sales_uploads])
            except ValueError as exc:
                st.error(str(exc))
            else:
                menu_data = menu_result.data
                st.subheader("1. Kiểm tra nguồn và chống trùng")
                st.dataframe(menu_result.files, width="stretch", hide_index=True, column_config={"Doanh thu": st.column_config.NumberColumn(format="%,.0f ₫")})
                if not menu_result.overlaps.empty:
                    st.dataframe(menu_result.overlaps, width="stretch", hide_index=True)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Dòng sau chống trùng", f"{len(menu_data):,}")
                c2.metric("Sản phẩm đã bán", f"{menu_data.item.nunique():,}")
                c3.metric("Số lượng", f"{menu_data.units_sold.sum():,.0f}")
                c4.metric("Doanh thu", money(float(menu_data.gross_sales_vnd.sum())))

                overview_tab, product_tab, prep_tab, quality_tab = st.tabs(["So sánh kỳ", "Hiệu quả sản phẩm", "Chuẩn bị theo mẫu", "Đối chiếu & chất lượng"])
                with overview_tab:
                    window = st.selectbox("Độ dài kỳ so sánh", [7, 14, 30], index=1, format_func=lambda value: f"{value} ngày")
                    comparison, recent_start, recent_end = period_comparison(menu_data, window)
                    st.dataframe(comparison, width="stretch", hide_index=True, column_config={"Doanh thu": st.column_config.NumberColumn(format="%,.0f ₫")})
                    daily_menu = menu_data.groupby("date", as_index=False).agg(gross_sales_vnd=("gross_sales_vnd", "sum"), units_sold=("units_sold", "sum"), products=("item", "nunique"))
                    st.plotly_chart(px.line(daily_menu, x="date", y="gross_sales_vnd", markers=True, title="Doanh thu Menu Sales theo ngày"), width="stretch")
                    all_dates = pd.date_range(menu_data.date.min(), menu_data.date.max())
                    missing_dates = all_dates.difference(menu_data.date.unique())
                    if len(missing_dates):
                        st.warning("Ngày không có dữ liệu: " + ", ".join(date.strftime("%d/%m/%Y") for date in missing_dates))

                with product_tab:
                    performance = product_performance(menu_data)
                    search_product = st.text_input("Tìm sản phẩm", key="menu_product_search")
                    if search_product:
                        performance = performance[performance.item.str.contains(search_product, case=False, na=False, regex=False)]
                    st.dataframe(performance, width="stretch", hide_index=True, column_config={
                        "gross_sales_vnd": st.column_config.NumberColumn("Doanh thu", format="%,.0f ₫"),
                        "average_selling_price": st.column_config.NumberColumn("Giá bán bình quân", format="%,.0f ₫"),
                        "revenue_per_selling_day": st.column_config.NumberColumn("Doanh thu/ngày bán", format="%,.0f ₫"),
                    })
                    st.download_button("Tải bảng hiệu quả sản phẩm", performance.to_csv(index=False).encode("utf-8-sig"), "menu_product_performance.csv", "text/csv")

                with prep_tab:
                    prep = preparation_board(menu_data)
                    suggestion = st.multiselect("Mức chuẩn bị", sorted(prep["Gợi ý chuẩn bị"].unique()), default=sorted(prep["Gợi ý chuẩn bị"].unique()))
                    prep_view = prep[prep["Gợi ý chuẩn bị"].isin(suggestion)]
                    st.dataframe(prep_view, width="stretch", hide_index=True, column_config={"gross_sales_vnd": st.column_config.NumberColumn("Doanh thu", format="%,.0f ₫")})
                    st.info("Gợi ý dựa trên tần suất 7/14/30 ngày, chỉ hỗ trợ chuẩn bị nguyên liệu; chủ cửa hàng vẫn cần xét mùa vụ và đơn đặt trước.")
                    st.download_button("Tải bảng chuẩn bị hoa", prep_view.to_csv(index=False).encode("utf-8-sig"), "flower_preparation_board.csv", "text/csv")

                with quality_tab:
                    changes = price_changes(menu_data)
                    st.subheader("Sản phẩm có nhiều mức giá bán suy ra")
                    st.dataframe(changes, width="stretch", hide_index=True, column_config={
                        "minimum_price": st.column_config.NumberColumn(format="%,.0f ₫"), "maximum_price": st.column_config.NumberColumn(format="%,.0f ₫"),
                        "latest_price": st.column_config.NumberColumn(format="%,.0f ₫"), "price_range": st.column_config.NumberColumn(format="%,.0f ₫"),
                    })
                    st.caption("Giá suy ra = doanh thu/số lượng; chênh lệch có thể do thay đổi giá hoặc cách Grab ghi nhận khuyến mãi.")
                    catalogue_upload = st.file_uploader("Tùy chọn: tải ZIP catalogue mới nhất để đối chiếu tên", type=["zip"], key="sales_catalogue_zip")
                    if catalogue_upload is not None:
                        try:
                            sales_package = read_grab_zip(catalogue_upload.getvalue())
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            current_names = set(sales_package.products["*ItemName"].astype(str))
                            reconciliation = product_performance(menu_data)
                            reconciliation["Khớp catalogue hiện tại"] = reconciliation.item.isin(current_names)
                            missing_current = reconciliation[~reconciliation["Khớp catalogue hiện tại"]]
                            matched_revenue = reconciliation.loc[reconciliation["Khớp catalogue hiện tại"], "gross_sales_vnd"].sum()
                            r1, r2, r3 = st.columns(3)
                            r1.metric("Tên đã bán", f"{len(reconciliation):,}")
                            r2.metric("Không khớp tên hiện tại", f"{len(missing_current):,}")
                            r3.metric("Doanh thu khớp tên", f"{matched_revenue/reconciliation.gross_sales_vnd.sum():.1%}")
                            st.dataframe(missing_current, width="stretch", hide_index=True)
                            st.download_button("Tải danh sách cần ánh xạ tên", missing_current.to_csv(index=False).encode("utf-8-sig"), "menu_catalogue_name_reconciliation.csv", "text/csv")
        else:
            st.info("Bắt đầu bằng cách tải file Menu Sales mới nhất. Có thể chọn nhiều file cùng lúc; ứng dụng sẽ cảnh báo phần bị chồng lặp.")

elif page == "Tạo sản phẩm hàng loạt":
    st.header("Tạo sản phẩm hoa hàng loạt từ bảng giá nhà cung cấp")
    st.info(
        "Quy trình đúng định dạng Grab: tải ZIP mẫu **Tạo món hàng loạt** mới nhất → "
        "chọn và rà soát sản phẩm → tải ảnh hợp lệ → xuất ZIP → tải ZIP lên GrabMerchant "
        "và chọn **Thêm vào thực đơn**."
    )
    st.markdown("[Xem hướng dẫn cập nhật hàng loạt chính thức của Grab ↗](https://help.grab.com/merchant/vi-vn/40001523)")
    with st.expander("Căn cứ xây dựng mô tả sản phẩm"):
        st.markdown(
            "Mô tả được viết theo đặc điểm hình thái ở cấp nhóm hoa, sau đó vẫn phải đối chiếu ảnh và quy cách của vựa. "
            "Các nguồn thực vật tham khảo gồm [Delphinium – NC State Extension](https://plants.ces.ncsu.edu/plants/delphinium/), "
            "[Hydrangea – NC State Extension](https://plants.ces.ncsu.edu/plants/hydrangea/) và "
            "[Waxflower – Royal Horticultural Society](https://www.rhs.org.uk/plants/62627/chamelaucium-uncinatum/details). "
            "Ứng dụng không tự thêm số cành, kích thước, xuất xứ, mùi hương hoặc độ bền khi bảng giá chưa cung cấp."
        )
    st.warning("Giá gốc trong ảnh đang được hiểu theo nghìn đồng và chưa rõ đơn vị bó/cành. Phải xác nhận với vựa trước khi tải lên GrabMerchant.")
    if not authorized:
        st.warning("Vui lòng đăng nhập bằng tài khoản được cấp quyền để tạo gói sản phẩm thật.")
    else:
        if "supplier_product_images" not in st.session_state:
            st.session_state.supplier_product_images = {}
        image_store = st.session_state.supplier_product_images
        # Giữ ảnh đã tải nếu phiên cũ còn dùng tên "Hoa bi trắng".
        for slot in range(1, 5):
            old_key = ("Hoa bi trắng", slot)
            new_key = ("Hoa baby trắng", slot)
            if old_key in image_store and new_key not in image_store:
                image_store[new_key] = image_store.pop(old_key)
        if "supplier_uploaded_products" not in st.session_state:
            st.session_state.supplier_uploaded_products = list(INITIAL_UPLOADED_PRODUCTS)
        uploaded_products = set(st.session_state.supplier_uploaded_products)
        multiplier = st.number_input("Hệ số giá bán", min_value=1.0, max_value=10.0, value=2.0, step=0.1, help="Giá bán = Giá gốc × Hệ số. Chưa bao gồm kiểm tra phí nền tảng và hao hụt.")
        all_supplier_products = supplier_product_table(multiplier)
        st.markdown("### Sản phẩm đã tải lên GrabMerchant")
        uploaded_rows = all_supplier_products[
            all_supplier_products["Tên sản phẩm"].isin(uploaded_products)
        ]
        if uploaded_rows.empty:
            st.info("Chưa có sản phẩm nào được đánh dấu đã tải lên GrabMerchant.")
        else:
            st.success(f"Đã xác nhận {len(uploaded_rows)} sản phẩm. Các sản phẩm này được ẩn khỏi danh sách tạo mới.")
            for start in range(0, len(uploaded_rows), 4):
                uploaded_columns = st.columns(4)
                for uploaded_column, (_, uploaded_product) in zip(
                    uploaded_columns, uploaded_rows.iloc[start:start + 4].iterrows()
                ):
                    product_name = str(uploaded_product["Tên sản phẩm"])
                    product_images = [
                        image_store[(product_name, slot)]["content"]
                        for slot in range(1, 5)
                        if (product_name, slot) in image_store
                    ]
                    with uploaded_column:
                        if product_images:
                            st.image(product_images[0], width="stretch")
                        else:
                            st.info("Chưa còn ảnh trong phiên")
                        st.markdown(f"**{product_name}**")
                        st.caption(f"{int(uploaded_product['Giá bán (₫)']):,.0f} ₫ · ✅ Đã up")
            with st.expander("Quản lý danh sách đã up"):
                st.caption("Bỏ đánh dấu nếu cần đưa sản phẩm trở lại danh sách tạo mới.")
                for name in sorted(uploaded_products):
                    if st.checkbox(f"{name} — đã up", value=True, key=f"uploaded_manager_{name}") is False:
                        uploaded_products.discard(name)
                        st.session_state.supplier_uploaded_products = sorted(uploaded_products)
                        st.rerun()

        st.markdown("### Bước 1 — Chọn nhóm sản phẩm thử nghiệm")
        available_supplier_products = all_supplier_products[
            ~all_supplier_products["Tên sản phẩm"].isin(uploaded_products)
        ]
        available_names = available_supplier_products["Tên sản phẩm"].astype(str).tolist()
        existing_trial_selection = st.session_state.get("supplier_trial_product_order", [])
        if any(name not in available_names for name in existing_trial_selection):
            st.session_state.supplier_trial_product_order = [
                name for name in existing_trial_selection if name in available_names
            ]
        trial_names = st.multiselect(
            "Chọn sản phẩm thử nghiệm theo thứ tự",
            options=available_names,
            default=[],
            help="Hãy chọn lần lượt 3–5 sản phẩm. Thứ tự chọn tại đây cũng là thứ tự trong CSV xuất sang Grab.",
            key="supplier_trial_product_order",
        )
        if trial_names:
            base_supplier = (
                available_supplier_products.set_index("Tên sản phẩm", drop=False)
                .loc[trial_names]
                .reset_index(drop=True)
            )
            base_supplier["Chọn tạo"] = True
            base_supplier.insert(0, "Thứ tự", range(1, len(base_supplier) + 1))
        else:
            base_supplier = available_supplier_products.iloc[0:0].copy()
            base_supplier.insert(0, "Thứ tự", pd.Series(dtype="int64"))
            st.warning("Chưa chọn sản phẩm thử nghiệm. Hãy chọn 3–5 sản phẩm trong ô phía trên.")
        st.markdown("### Bước 2 — Rà soát tên, giá và mô tả")
        supplier_editor = st.data_editor(
            base_supplier,
            width="stretch",
            hide_index=True,
            disabled=["Thứ tự", "Chọn tạo", "Hệ số giá", "Giá bán (₫)", "Tìm ảnh tham chiếu", "Tên file ảnh 1", "Tên file ảnh 2", "Tên file ảnh 3", "Tên file ảnh 4"],
            column_config={
                "Chọn tạo": st.column_config.CheckboxColumn(required=True),
                "Giá gốc (₫)": st.column_config.NumberColumn(format="%,.0f ₫", min_value=0),
                "Giá bán (₫)": st.column_config.NumberColumn(format="%,.0f ₫"),
                "Tình trạng tên": st.column_config.SelectboxColumn(options=["Cần xác minh với vựa", "Đã chuẩn hóa"], required=True),
                "Tìm ảnh tham chiếu": st.column_config.LinkColumn("Tìm ảnh tham chiếu", display_text="Mở tìm kiếm ảnh ↗"),
            },
            key="supplier_product_editor_v2",
        )
        supplier_editor = recalculate_prices(supplier_editor, multiplier)
        selected_supplier = supplier_editor[supplier_editor["Chọn tạo"].astype(bool)]
        c1, c2, c3 = st.columns(3)
        c1.metric("Sản phẩm được chọn", f"{len(selected_supplier):,}")
        c2.metric("Chưa xác minh tên", f"{selected_supplier['Tình trạng tên'].eq('Cần xác minh với vựa').sum():,}")
        c3.metric("Ảnh đã lưu", f"{len(image_store):,}")
        st.download_button("Tải bảng sản phẩm dự thảo", supplier_editor.to_csv(index=False).encode("utf-8-sig"), "supplier_products_draft.csv", "text/csv")

        st.markdown("### Bước 3 — Thêm ảnh theo từng sản phẩm")
        st.info("Liên kết tìm kiếm chỉ để nhận diện. Hãy tải lên ảnh do cửa hàng/vựa cung cấp hoặc ảnh có quyền sử dụng; không tự động sao chép ảnh Internet có bản quyền vào gian hàng.")
        st.caption("Mỗi sản phẩm có tối đa 4 ảnh. Có thể nhấp phải **Sao chép hình ảnh**, bấm vào vùng dán rồi nhấn **Ctrl+V**; hoặc kéo thả/chọn file JPG/PNG. Ứng dụng tự đặt tên an toàn.")
        selected_names = selected_supplier["Tên sản phẩm"].astype(str).tolist()
        if selected_names:
            image_product = st.selectbox("Chọn sản phẩm để thêm ảnh", selected_names, key="supplier_image_product")
            for first_slot in (1, 3):
                image_columns = st.columns(2)
                for image_column, slot in zip(image_columns, range(first_slot, first_slot + 2)):
                    image_key = (image_product, slot)
                    with image_column:
                        st.markdown(f"**Ảnh {slot}**")
                        pasted = paste_image_zone(
                            f"Dán vào ảnh {slot}", key=f"event_paste_{image_product}_{slot}"
                        )
                        if pasted:
                            try:
                                pasted_content, pasted_extension, pasted_token = decode_pasted_image(pasted)
                            except ValueError as exc:
                                st.error(str(exc))
                            else:
                                token_key = f"processed_event_paste_{image_product}_{slot}"
                                if st.session_state.get(token_key) != pasted_token:
                                    filename = safe_image_filename(image_product, slot, pasted_extension)
                                    image_store[image_key] = {"filename": filename, "content": pasted_content}
                                    st.session_state[token_key] = pasted_token
                                    st.success("Đã dán và lưu ảnh.")
                        uploaded = st.file_uploader(
                            f"Hoặc kéo thả/chọn file ảnh {slot}",
                            type=["jpg", "png"],
                            key=f"product_image_{image_product}_{slot}",
                        )
                        if uploaded is not None:
                            extension = uploaded.name.rsplit(".", 1)[-1].lower()
                            filename = safe_image_filename(image_product, slot, extension)
                            image_store[image_key] = {"filename": filename, "content": uploaded.getvalue()}
                        if image_key in image_store:
                            stored = image_store[image_key]
                            st.image(stored["content"], caption=stored["filename"], width="stretch")
                            if len(stored["content"]) > 2 * 1024 * 1024:
                                st.error("Ảnh vượt 2 MB; hãy giảm kích thước trước khi xuất ZIP.")
                            if st.button("Xóa ảnh", key=f"remove_product_image_{image_product}_{slot}"):
                                del image_store[image_key]
                                st.rerun()
        else:
            st.warning("Hãy chọn ít nhất một sản phẩm trước khi thêm ảnh.")

        selected_name_set = set(selected_names)
        selected_image_store = {
            key: item for key, item in image_store.items() if key[0] in selected_name_set
        }
        image_map = {item["filename"]: item["content"] for item in selected_image_store.values()}
        for row_index, product in supplier_editor.iterrows():
            product_name = str(product["Tên sản phẩm"])
            for slot in range(1, 5):
                stored = image_store.get((product_name, slot))
                supplier_editor.at[row_index, f"Tên file ảnh {slot}"] = stored["filename"] if stored else ""
        if image_map:
            st.success(f"Đã lưu {len(image_map)} ảnh của {len({key[0] for key in selected_image_store}):,} sản phẩm đang chọn.")

        st.markdown("### Bước 4 — Kiểm tra mức độ hoàn thành")
        progress_rows = []
        for _, product in selected_supplier.iterrows():
            product_name = str(product["Tên sản phẩm"])
            product_images = [
                image_store[(product_name, slot)]
                for slot in range(1, 5)
                if (product_name, slot) in image_store
            ]
            reasons = []
            if not product_images:
                reasons.append("chưa có ảnh")
            if any(len(image["content"]) > 2 * 1024 * 1024 for image in product_images):
                reasons.append("có ảnh vượt 2 MB")
            if str(product["Tình trạng tên"]) != "Đã chuẩn hóa":
                reasons.append("chưa xác minh tên")
            if not str(product["Mô tả"]).strip():
                reasons.append("thiếu mô tả")
            if pd.isna(product["Giá bán (₫)"]) or float(product["Giá bán (₫)"]) <= 0:
                reasons.append("giá bán chưa hợp lệ")
            ready = not reasons
            progress_rows.append({
                "Thứ tự": int(product["Thứ tự"]),
                "Sản phẩm": product_name,
                "Ảnh": f"{len(product_images)}/4",
                "Tên": "Đã xác minh" if str(product["Tình trạng tên"]) == "Đã chuẩn hóa" else "Cần xác minh",
                "Giá bán": int(product["Giá bán (₫)"]) if pd.notna(product["Giá bán (₫)"]) else 0,
                "Trạng thái": "✅ Sẵn sàng xuất" if ready else "⏳ Chưa hoàn thành",
                "Cần bổ sung": "—" if ready else ", ".join(reasons),
            })
        progress_frame = pd.DataFrame(progress_rows)
        ready_count = int(progress_frame["Trạng thái"].eq("✅ Sẵn sàng xuất").sum()) if not progress_frame.empty else 0
        selected_count = len(progress_frame)
        p1, p2, p3 = st.columns(3)
        p1.metric("Đã hoàn thành", f"{ready_count}/{selected_count}")
        p2.metric("Chưa hoàn thành", f"{selected_count - ready_count}")
        p3.metric("Tổng ảnh hợp lệ đã gắn", f"{len(image_map)}")
        st.progress(ready_count / selected_count if selected_count else 0.0)
        if not progress_frame.empty:
            st.dataframe(
                progress_frame,
                width="stretch",
                hide_index=True,
                column_config={"Giá bán": st.column_config.NumberColumn(format="%,.0f ₫")},
            )

        st.markdown("#### Nhật ký sản phẩm đã thao tác trong phiên")
        touched_names = [
            name for name in all_supplier_products["Tên sản phẩm"].astype(str)
            if name not in uploaded_products and any(key[0] == name for key in image_store)
        ]
        globally_ready_names = {
            str(row["Tên sản phẩm"])
            for _, row in all_supplier_products.iterrows()
            if str(row["Tình trạng tên"]) == "Đã chuẩn hóa"
            and str(row["Mô tả"]).strip()
            and float(row["Giá bán (₫)"]) > 0
            and any((str(row["Tên sản phẩm"]), slot) in image_store for slot in range(1, 5))
            and all(
                len(image_store[(str(row["Tên sản phẩm"]), slot)]["content"]) <= 2 * 1024 * 1024
                for slot in range(1, 5)
                if (str(row["Tên sản phẩm"]), slot) in image_store
            )
        }
        tracking_rows = []
        if touched_names:
            st.caption(
                "Ứng dụng tự ghi nhận sản phẩm đã có ảnh. Sau khi tải ZIP lên GrabMerchant và bấm "
                "**Thêm vào thực đơn**, hãy đánh dấu ô xác nhận tương ứng."
            )
            for name in touched_names:
                count = sum((name, slot) in image_store for slot in range(1, 5))
                was_uploaded = name in uploaded_products
                applied = st.checkbox(
                    f"{name} — {count}/4 ảnh — Đã áp dụng trên GrabMerchant",
                    value=was_uploaded,
                    key=f"grab_applied_{name}",
                    help="Chỉ đánh dấu sau khi GrabMerchant đã xử lý file và không báo lỗi.",
                )
                if applied != was_uploaded:
                    if applied:
                        uploaded_products.add(name)
                    else:
                        uploaded_products.discard(name)
                    st.session_state.supplier_uploaded_products = sorted(uploaded_products)
                    st.rerun()
                if applied:
                    status = "✅ Đã xác nhận cập nhật trên Grab"
                elif name in globally_ready_names:
                    status = "🟢 Đã chuẩn bị xong trên ứng dụng"
                else:
                    status = "🟡 Đã thêm ảnh, cần kiểm tra tiếp"
                tracking_rows.append({"Sản phẩm": name, "Ảnh đã lưu": f"{count}/4", "Trạng thái": status})
            applied_count = sum(row["Trạng thái"].startswith("✅") for row in tracking_rows)
            t1, t2, t3 = st.columns(3)
            t1.metric("Đã thao tác trên ứng dụng", len(tracking_rows))
            t2.metric("Đã chuẩn bị xong", sum(row["Trạng thái"].startswith(("🟢", "✅")) for row in tracking_rows))
            t3.metric("Đã xác nhận trên Grab", applied_count)
            st.dataframe(pd.DataFrame(tracking_rows), width="stretch", hide_index=True)
        else:
            st.info("Chưa có sản phẩm nào được thêm ảnh trong phiên này.")

        preview_products = [row for row in progress_rows if row["Ảnh"] != "0/4"]
        st.markdown("### Bước 5 — Xem trước gian hàng Grab")
        if not preview_products:
            st.info("Sản phẩm sẽ xuất hiện ở đây sau khi có ít nhất một ảnh.")
        else:
            st.caption("Giao diện minh họa dùng chính ảnh, tên, giá và mô tả hiện có; không phải màn hình GrabMerchant chính thức.")
            for start in range(0, len(preview_products), 3):
                card_columns = st.columns(3)
                for card_column, status_row in zip(card_columns, preview_products[start:start + 3]):
                    product_name = status_row["Sản phẩm"]
                    product = selected_supplier[selected_supplier["Tên sản phẩm"].eq(product_name)].iloc[0]
                    product_images = [
                        image_store[(product_name, slot)]
                        for slot in range(1, 5)
                        if (product_name, slot) in image_store
                    ]
                    with card_column:
                        st.image(product_images[0]["content"], width="stretch")
                        st.markdown(f"#### {product_name}")
                        st.markdown(f"**{int(product['Giá bán (₫)']):,.0f} ₫**")
                        st.caption(str(product["Mô tả"]))
                        st.success(f"Có bán · {len(product_images)}/4 ảnh")
                        if len(product_images) > 1:
                            thumbnail_columns = st.columns(min(3, len(product_images) - 1))
                            for thumbnail_column, image in zip(thumbnail_columns, product_images[1:]):
                                thumbnail_column.image(image["content"], width="stretch")

        st.markdown("### Bước 6 — Xuất gói Tạo món hàng loạt")
        st.caption("Trên GrabMerchant, chọn Thực đơn → Cập nhật hàng loạt → Tạo món hàng loạt và tải mẫu ZIP mới nhất, sau đó đưa nguyên ZIP đó vào đây. Ứng dụng giữ nguyên dòng hướng dẫn, tên cột, readme và danh sách danh mục của mẫu.")
        create_template = st.file_uploader("Tải ZIP mẫu Tạo món hàng loạt của GrabMerchant", type=["zip"], key="grab_create_template")
        if create_template is not None:
            if not selected_count or ready_count < selected_count:
                st.error("Chưa thể xuất ZIP: hãy hoàn thành tất cả sản phẩm trong bảng tiến độ phía trên.")
            else:
                try:
                    create_zip, created_names = build_create_items_zip(create_template.getvalue(), supplier_editor, image_map)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Gói hợp lệ đã sẵn sàng cho {len(created_names):,} sản phẩm.")
                    confirmed_create = st.checkbox("Tôi đã xác nhận tên, đơn vị mua, giá gốc, giá bán và quyền sử dụng ảnh", key="confirm_create_items")
                    if confirmed_create:
                        st.download_button("Tải ZIP Tạo món hàng loạt", create_zip, "grab_create_items_supplier_flowers.zip", "application/zip", type="primary")
                        st.warning("Hãy tải thực đơn hiện tại để dự phòng và thử trước 3–5 sản phẩm. Grab không hỗ trợ hoàn tác cập nhật hàng loạt; chỉ xác nhận Thêm vào thực đơn khi trang kiểm tra không báo lỗi.")

elif page == "MIWI & đánh giá khách hàng":
    st.header("Chất lượng thực hiện đơn và đánh giá khách hàng")
    reviews["rating"] = pd.to_numeric(reviews.rating)
    low = reviews.rating.le(2)
    cols = st.columns(5)
    cols[0].metric("Điểm trung bình", f"{reviews.rating.mean():.2f}/5")
    cols[1].metric("Tỷ lệ 4–5 sao", f"{reviews.rating.ge(4).mean():.1%}")
    cols[2].metric("Trả lời đánh giá thấp", f"{reviews.loc[low, 'has_reply'].mean():.1%}")
    cols[3].metric("MIWI Missing", int(miwi.missing_reported.sum()))
    cols[4].metric("MIWI Wrong", int(miwi.wrong_reported.sum()))
    left, right = st.columns(2)
    dist = reviews.groupby("rating", as_index=False).size()
    left.plotly_chart(px.bar(dist, x="rating", y="size", title="Phân bố điểm đánh giá", color_discrete_sequence=["#00B14F"]), width="stretch")
    events = miwi_events.groupby(["hour", "disposition"], as_index=False).size()
    right.plotly_chart(px.bar(events, x="hour", y="size", color="disposition", barmode="group", title="Sự cố MIWI theo giờ"), width="stretch")
    st.warning("Mẫu MIWI và Customer Review còn nhỏ; các kết quả chỉ dùng để phát hiện tín hiệu cần kiểm tra, không dùng để kết luận nhân quả.")

elif page == "Phân tích thực nghiệm":
    st.header("Phân tích thực nghiệm trên dữ liệu kinh doanh GrabMart")
    st.caption("Thực nghiệm sử dụng tám bảng dữ liệu trong giai đoạn 25/05–31/08/2026 để đánh giá hiệu quả danh mục, chất lượng dữ liệu và các yếu tố liên quan đến khả năng ghi nhận bán hàng.")
    tabs = st.tabs([
        "1. Tập trung & tần suất",
        "2. Nhóm & giá",
        "3. Chất lượng dữ liệu",
        "4. Khuyến mãi",
        "5. Kiểm định & mô hình",
        "6. MIWI & Review",
    ])
    with tabs[0]:
        st.subheader("Mức sử dụng danh mục và độ tập trung doanh thu")
        st.dataframe(concentration(score), width="stretch", hide_index=True)
        bands = frequency_bands(score)
        st.subheader("Tần suất bán và vận tốc")
        st.dataframe(bands, width="stretch", hide_index=True, column_config={
            "Tỷ trọng sản phẩm": st.column_config.NumberColumn(format="percent"),
            "Tỷ trọng số lượng": st.column_config.NumberColumn(format="percent"),
            "Tỷ trọng doanh thu": st.column_config.NumberColumn(format="percent"),
        })
        left, right = st.columns(2)
        left.plotly_chart(px.bar(bands, x="Dải ngày bán", y="Sản_phẩm", title="Sản phẩm theo dải ngày bán"), width="stretch")
        right.plotly_chart(px.bar(bands, x="Dải ngày bán", y="Tỷ trọng doanh thu", title="Tỷ trọng doanh thu theo dải ngày bán"), width="stretch")
        st.subheader("Phân tích độ nhạy của ngưỡng ngày bán")
        st.dataframe(sensitivity(score), width="stretch", hide_index=True, column_config={
            "Tỷ trọng sản phẩm đã bán": st.column_config.NumberColumn(format="percent"),
            "Tỷ trọng doanh thu": st.column_config.NumberColumn(format="percent"),
        })
        st.subheader("Kết quả ABC–XYZ và điểm ưu tiên")
        abcxyz = score.groupby(["abc", "xyz", "priority_label"], as_index=False).agg(
            products=("product_name_current", "size"), gross_revenue=("gross_revenue", "sum"), units_sold=("units_sold", "sum")
        )
        st.dataframe(abcxyz, width="stretch", hide_index=True)
        sold_score = score.loc[score.recorded_sales.astype(bool)].copy()
        sold_score["sales_velocity"] = sold_score.units_sold / sold_score.selling_days.replace(0, np.nan)
        sold_score["revenue_velocity"] = sold_score.gross_revenue / sold_score.selling_days.replace(0, np.nan)
        v1, v2, v3 = st.columns(3)
        v1.metric("Trung vị ngày bán", f"{sold_score.selling_days.median():.1f} ngày")
        v2.metric("Trung vị tốc độ bán", f"{sold_score.sales_velocity.median():.2f} SP/ngày bán")
        v3.metric("Trung vị doanh thu/ngày bán", money(float(sold_score.revenue_velocity.median())))
        managerial = score.groupby("managerial_class", as_index=False).agg(
            products=("product_name_current", "size"), gross_revenue=("gross_revenue", "sum"), units_sold=("units_sold", "sum")
        )
        managerial["product_share"] = managerial.products / managerial.products.sum()
        managerial["revenue_share"] = managerial.gross_revenue / managerial.gross_revenue.sum()
        st.subheader("Phân lớp quản trị kết hợp doanh thu và tần suất")
        st.dataframe(managerial, width="stretch", hide_index=True)

    with tabs[1]:
        category = assortment_performance(score, "product_group")
        price = assortment_performance(score, "price_segment")
        st.subheader("Hiệu suất theo nhóm sản phẩm")
        st.dataframe(category, width="stretch", hide_index=True)
        st.plotly_chart(px.bar(category, x="product_group", y="recorded_sales_rate", title="Tỷ lệ sản phẩm có bán theo nhóm"), width="stretch")
        st.subheader("Hiệu suất theo phân khúc giá")
        st.dataframe(price, width="stretch", hide_index=True)
        st.plotly_chart(px.bar(price, x="price_segment", y="recorded_sales_rate", title="Tỷ lệ sản phẩm có bán theo phân khúc giá"), width="stretch")
        cell = score.groupby(["product_group", "price_segment"], as_index=False).agg(
            active_products=("product_name_current", "size"), products_with_sales=("recorded_sales", "sum")
        )
        cell["recorded_sales_rate"] = cell.products_with_sales / cell.active_products
        matrix = cell.pivot(index="product_group", columns="price_segment", values="recorded_sales_rate")
        st.subheader("Ma trận nhóm sản phẩm × phân khúc giá")
        st.plotly_chart(px.imshow(matrix, text_auto=".1%", color_continuous_scale="Greens", aspect="auto"), width="stretch")
        st.dataframe(cell, width="stretch", hide_index=True)

    with tabs[2]:
        st.subheader("Kiểm toán dữ liệu catalogue")
        st.dataframe(quality_summary(score), width="stretch", hide_index=True, column_config={"Tỷ lệ": st.column_config.NumberColumn(format="percent")})
        st.dataframe(score[[
            "product_name_current", "product_group", "duplicate_name", "duplicate_with_price_diff",
            "desc_missing_any", "photo_count_min", "sku_present_any", "barcode_present_any", "review_priority_score"
        ]].sort_values("review_priority_score", ascending=False), width="stretch", hide_index=True)

    with tabs[3]:
        promo, by_offer = promotion_summary(offers, bundle["sales_daily"])
        st.subheader("Cường độ khuyến mãi")
        st.dataframe(promo, width="stretch", hide_index=True)
        st.subheader("Chương trình theo mức chi")
        st.dataframe(by_offer, width="stretch", hide_index=True)
        st.warning("Doanh thu gán cho các offer có thể chồng lặp. Không cộng các chương trình để suy ra doanh thu tăng thêm và không diễn giải như quan hệ nhân quả.")

    with tabs[4]:
        tests = pd.DataFrame([
            cramer_test(score, "product_group"),
            cramer_test(score, "price_segment"),
            duplicate_test(score),
        ])
        st.subheader("Kiểm định Chi-square và Cramér’s V")
        st.dataframe(tests, width="stretch", hide_index=True)
        st.subheader("Hồi quy logistic khám phá — 5-fold cross-validation")
        cv = cached_logistic_cv(score)
        st.dataframe(cv, width="stretch", hide_index=True)
        st.caption(f"Tỷ lệ nền sản phẩm có bán: {score.recorded_sales.mean():.1%}. Mô hình dùng nhóm sản phẩm, phân khúc giá và sáu cờ chất lượng dữ liệu; kết quả chỉ thể hiện liên hệ, không chứng minh nhân quả.")

    with tabs[5]:
        st.subheader("Phân tích vận hành mở rộng")
        st.dataframe(operational_extension(miwi, reviews), width="stretch", hide_index=True)
        st.warning("MIWI và Customer Review có cỡ mẫu nhỏ, chỉ dùng mô tả tín hiệu vận hành. Thông tin nhận dạng khách hàng không được hiển thị trong phần thực nghiệm.")

elif page == "Khám phá bảng dữ liệu":
    st.header("Khám phá dữ liệu phân tích an toàn")
    st.info(
        "Khu vực này chỉ hiển thị và cho tải các cột phục vụ phân tích. "
        "Tên khách hàng, nội dung nhận xét/phản hồi, mã cửa hàng và mã đơn hàng "
        "được loại bỏ ngay khi truy vấn BigQuery."
    )
    table_labels = {
        "sales_daily": "Doanh số theo ngày",
        "menu_sales": "Doanh số theo sản phẩm/menu",
        "offers": "Chương trình khuyến mãi",
        "peak_hours": "Giao dịch theo giờ",
        "product_scoring": "Điểm và phân nhóm sản phẩm",
        "miwi_item_breakdown": "MIWI theo sản phẩm (đã bỏ mã đơn)",
        "miwi_heatmap": "MIWI theo thời gian",
        "customer_reviews": "Chỉ số đánh giá (không có nội dung/khách hàng)",
    }
    selected_table = st.selectbox(
        "Chọn bảng",
        list(bundle.tables),
        format_func=lambda name: f"{table_labels.get(name, name)} ({name})",
    )
    raw_table = bundle.tables[selected_table].copy()
    c1, c2, c3 = st.columns(3)
    c1.metric("Số dòng", f"{len(raw_table):,}")
    c2.metric("Số cột", f"{len(raw_table.columns):,}")
    missing_cells = int(raw_table.isna().sum().sum()) if not raw_table.empty else 0
    total_cells = int(raw_table.shape[0] * raw_table.shape[1])
    c3.metric("Tỷ lệ ô thiếu", f"{missing_cells / total_cells:.1%}" if total_cells else "0.0%")

    search = st.text_input("Tìm trong dữ liệu", placeholder="Nhập tên sản phẩm, nhóm, trạng thái…")
    filtered = raw_table
    if search and not raw_table.empty:
        text_columns = raw_table.select_dtypes(include=["object", "string", "category"]).columns
        if len(text_columns):
            mask = raw_table[text_columns].astype("string").apply(
                lambda column: column.str.contains(search, case=False, na=False, regex=False)
            ).any(axis=1)
            filtered = raw_table.loc[mask]
        else:
            st.info("Bảng này không có cột văn bản để tìm kiếm.")

    limit = st.slider("Số dòng hiển thị", 10, 500, 100, step=10)
    st.caption(f"Đang hiển thị {min(len(filtered), limit):,}/{len(filtered):,} dòng phù hợp; bảng gốc có {len(raw_table):,} dòng.")
    st.dataframe(filtered.head(limit), width="stretch", hide_index=True)
    st.download_button(
        "Tải dữ liệu phân tích đã lọc và khử trường nhạy cảm",
        filtered.to_csv(index=False).encode("utf-8-sig"),
        f"{selected_table}_filtered.csv",
        "text/csv",
    )

    with st.expander("Cấu trúc và chất lượng cột"):
        schema = pd.DataFrame({
            "Tên cột": raw_table.columns,
            "Kiểu dữ liệu": [str(dtype) for dtype in raw_table.dtypes],
            "Số giá trị khác nhau": [raw_table[column].nunique(dropna=True) for column in raw_table.columns],
            "Số ô thiếu": [int(raw_table[column].isna().sum()) for column in raw_table.columns],
            "Tỷ lệ thiếu": [float(raw_table[column].isna().mean()) if len(raw_table) else 0 for column in raw_table.columns],
        })
        st.dataframe(
            schema,
            width="stretch",
            hide_index=True,
            column_config={"Tỷ lệ thiếu": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)},
        )
    st.info("Màn hình này chỉ đọc dữ liệu đã giới hạn cột. Việc sửa bảng nguồn phải được thực hiện qua quy trình ETL/BigQuery đã kiểm soát.")

else:
    st.header("Trung tâm hành động")
    st.markdown("""
<div class="workflow">
  <b>Quy trình:</b> BigQuery cung cấp dữ liệu → ứng dụng phát hiện vấn đề và đề xuất →
  chủ cửa hàng xác minh → thực hiện trên GrabMerchant → theo dõi kết quả ở kỳ tiếp theo.
</div>
""", unsafe_allow_html=True)
    tasks = action_list(score, reviews, miwi)
    edited_tasks = st.data_editor(
        tasks,
        width="stretch",
        hide_index=True,
        disabled=["Mã", "Mức độ", "Công việc đề xuất", "Căn cứ dữ liệu", "Khu vực GrabMerchant"],
        column_config={
            "Trạng thái": st.column_config.SelectboxColumn(
                "Trạng thái",
                options=["Chưa thực hiện", "Đang xác minh", "Đã thực hiện", "Không áp dụng"],
                required=True,
            )
        },
        key="action_editor",
    )
    done = int(edited_tasks["Trạng thái"].isin(["Đã thực hiện", "Không áp dụng"]).sum())
    c1, c2, c3 = st.columns([1, 1, 1.4])
    c1.metric("Tổng công việc", len(edited_tasks))
    c2.metric("Đã xử lý", f"{done}/{len(edited_tasks)}")
    c3.link_button("Đăng nhập GrabMerchant để thực hiện ↗", "https://merchant.grab.com/", width="stretch")
    st.download_button(
        "Tải danh sách hành động đã cập nhật",
        edited_tasks.to_csv(index=False).encode("utf-8-sig"),
        "grabmart_action_register.csv",
        "text/csv",
    )
    with st.expander("Hướng dẫn thực hiện và kiểm chứng", expanded=True):
        st.markdown("""
1. Mở dashboard tương ứng để kiểm tra căn cứ dữ liệu.
2. Xác minh yếu tố mùa vụ, tồn kho và chiến lược kinh doanh trước khi quyết định.
3. Mở GrabMerchant chính thức; đăng nhập trực tiếp với Grab và thực hiện tại khu vực được gợi ý.
4. Quay lại ứng dụng, cập nhật **Trạng thái** rồi tải tệp CSV để lưu bằng chứng.
5. Nạp dữ liệu kỳ tiếp theo vào BigQuery và so sánh chỉ tiêu trước–sau.
""")
    st.info("Ứng dụng không yêu cầu hoặc lưu mật khẩu Grab. Phiên đăng nhập và mọi thay đổi nghiệp vụ chỉ diễn ra trên cổng GrabMerchant chính thức.")

st.divider()
st.caption("Ứng dụng hỗ trợ quyết định; không tự động xóa sản phẩm, sửa giá, tạo khuyến mãi hoặc phản hồi khách hàng.")

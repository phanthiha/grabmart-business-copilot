from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src.data import load_data
from src.metrics import action_list, catalogue_issues, gini
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
    use_demo = st.toggle("Dùng dữ liệu demo an toàn", value=False, help="Tự động bật nếu chưa cấu hình BigQuery secrets.")
    page = st.radio("Chức năng", [
        "Tổng quan kinh doanh",
        "Danh mục ABC–XYZ",
        "Kiểm toán catalogue",
        "MIWI & đánh giá khách hàng",
        "Phân tích thực nghiệm",
        "Khám phá bảng dữ liệu",
        "Danh sách công việc",
    ])
    st.divider()
    st.markdown("**Thực hiện quyết định**")
    st.caption("Ứng dụng phân tích dữ liệu; GrabMerchant là nơi xác nhận và thực hiện thay đổi.")
    st.link_button("Mở GrabMerchant chính thức ↗", "https://merchant.grab.com/", width="stretch")

bundle = load_data(use_demo)
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
    issues = catalogue_issues(score)
    left, right = st.columns([1.2, 1])
    left.plotly_chart(px.bar(issues, x="Số sản phẩm", y="Vấn đề", orientation="h", color="Số sản phẩm", color_continuous_scale="Greens"), width="stretch")
    right.dataframe(issues, width="stretch", hide_index=True)
    issue_filter = st.selectbox("Danh sách cần xử lý", issues["Vấn đề"])
    masks = {
        "Trùng tên": score.duplicate_name,
        "Trùng tên nhưng khác giá": score.duplicate_with_price_diff,
        "Thiếu mô tả": score.desc_missing_any,
        "Chỉ có một ảnh": score.photo_count_min.eq(1),
        "Thiếu SKU": ~score.sku_present_any.astype(bool),
        "Thiếu barcode": ~score.barcode_present_any.astype(bool),
    }
    audit = score.loc[masks[issue_filter], ["product_name_current", "product_group", "price_segment", "gross_revenue", "priority_label"]]
    st.dataframe(audit, width="stretch", hide_index=True)
    st.download_button("Tải danh sách cần sửa", audit.to_csv(index=False).encode("utf-8-sig"), "catalogue_audit.csv", "text/csv")

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
    st.header("Khám phá bảng dữ liệu BigQuery")
    table_labels = {
        "sales_daily": "Doanh số theo ngày",
        "menu_sales": "Doanh số theo sản phẩm/menu",
        "offers": "Chương trình khuyến mãi",
        "peak_hours": "Giao dịch theo giờ",
        "product_scoring": "Điểm và phân nhóm sản phẩm",
        "miwi_item_breakdown": "Chi tiết MIWI theo sản phẩm",
        "miwi_heatmap": "MIWI theo thời gian",
        "customer_reviews": "Đánh giá khách hàng",
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
        "Tải dữ liệu đang lọc",
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
    st.info("Màn hình này chỉ đọc dữ liệu. Việc sửa bảng nguồn phải được thực hiện qua quy trình ETL/BigQuery đã kiểm soát.")

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

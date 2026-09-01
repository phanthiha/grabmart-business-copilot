from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.data import load_data
from src.metrics import action_list, catalogue_issues, gini


st.set_page_config(page_title="GrabMart Business Copilot", page_icon="🛒", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.7rem; padding-bottom: 3rem;}
[data-testid="stMetric"] {background:#fff; border:1px solid #dce9e1; border-radius:14px; padding:14px;}
.hero {background:linear-gradient(120deg,#003d29,#00b14f); color:white; padding:24px 28px; border-radius:18px; margin-bottom:18px;}
.hero h1 {margin:0 0 6px 0; font-size:2rem;}
.hero p {margin:0; opacity:.92;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>GrabMart Assortment & Operations Copilot</h1>
  <p>Hỗ trợ chủ cửa hàng đánh giá danh mục, chất lượng vận hành và tiếng nói khách hàng bằng BigQuery.</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Điều khiển")
    use_demo = st.toggle("Dùng dữ liệu demo an toàn", value=False, help="Tự động bật nếu chưa cấu hình BigQuery secrets.")
    page = st.radio("Chức năng", [
        "Tổng quan kinh doanh",
        "Danh mục ABC–XYZ",
        "Kiểm toán catalogue",
        "MIWI & đánh giá khách hàng",
        "Danh sách công việc",
    ])
    st.divider()
    st.link_button("Mở GrabMerchant Portal", "https://merchant.grab.com/", use_container_width=True)

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
    left.plotly_chart(px.line(daily, x="date", y="gross_sales_vnd", title="Doanh số theo ngày", markers=True), use_container_width=True)
    hour = peak.groupby("hour", as_index=False).transaction_count.sum()
    right.plotly_chart(px.bar(hour, x="hour", y="transaction_count", title="Giao dịch theo giờ", color_discrete_sequence=["#00B14F"]), use_container_width=True)

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
    left.plotly_chart(px.imshow(matrix, text_auto=True, color_continuous_scale="Greens", title="Ma trận ABC–XYZ"), use_container_width=True)
    priority = view.groupby("priority_label", as_index=False).agg(products=("product_name_current", "size"), revenue=("gross_revenue", "sum"))
    right.plotly_chart(px.bar(priority, x="products", y="priority_label", orientation="h", color="priority_label", title="Mức ưu tiên rà soát"), use_container_width=True)
    columns = ["product_name_current", "product_group", "price_segment", "gross_revenue", "units_sold", "selling_days", "abc", "xyz", "review_priority_score", "priority_label"]
    st.dataframe(view[columns].sort_values(["review_priority_score", "gross_revenue"], ascending=[False, True]), use_container_width=True, hide_index=True)
    st.download_button("Tải danh sách sản phẩm", view[columns].to_csv(index=False).encode("utf-8-sig"), "product_review.csv", "text/csv")
    st.info("Điểm ưu tiên là công cụ sàng lọc. Sản phẩm có điểm cao không đồng nghĩa phải tự động xóa khỏi GrabMart.")

elif page == "Kiểm toán catalogue":
    st.header("Kiểm toán chất lượng catalogue")
    issues = catalogue_issues(score)
    left, right = st.columns([1.2, 1])
    left.plotly_chart(px.bar(issues, x="Số sản phẩm", y="Vấn đề", orientation="h", color="Số sản phẩm", color_continuous_scale="Greens"), use_container_width=True)
    right.dataframe(issues, use_container_width=True, hide_index=True)
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
    st.dataframe(audit, use_container_width=True, hide_index=True)
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
    left.plotly_chart(px.bar(dist, x="rating", y="size", title="Phân bố điểm đánh giá", color_discrete_sequence=["#00B14F"]), use_container_width=True)
    events = miwi_events.groupby(["hour", "disposition"], as_index=False).size()
    right.plotly_chart(px.bar(events, x="hour", y="size", color="disposition", barmode="group", title="Sự cố MIWI theo giờ"), use_container_width=True)
    st.warning("Mẫu MIWI và Customer Review còn nhỏ; các kết quả chỉ dùng để phát hiện tín hiệu cần kiểm tra, không dùng để kết luận nhân quả.")

else:
    st.header("Danh sách công việc ưu tiên")
    tasks = action_list(score, reviews, miwi)
    st.dataframe(tasks, use_container_width=True, hide_index=True)
    st.download_button("Tải danh sách công việc", tasks.to_csv(index=False).encode("utf-8-sig"), "action_list.csv", "text/csv")
    st.subheader("Quy trình sử dụng")
    st.markdown("""
1. Kiểm tra bằng chứng trên dashboard.
2. Xác nhận vai trò mùa vụ hoặc chiến lược của sản phẩm.
3. Chỉnh catalogue hoặc vận hành trên GrabMerchant Portal.
4. Ghi nhận hành động đã thực hiện.
5. Theo dõi chỉ tiêu trong kỳ dữ liệu tiếp theo.
""")

st.divider()
st.caption("Ứng dụng hỗ trợ quyết định; không tự động xóa sản phẩm, sửa giá, tạo khuyến mãi hoặc phản hồi khách hàng.")


from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account


# Chỉ đọc các trường cần cho phân tích. Các trường nhận dạng/chi tiết thô như
# customer, review, reply, store_id, merchant, order_id và short_order_number
# cố ý không xuất hiện trong danh sách này.
SAFE_COLUMNS = {
    "sales_daily": (
        "date", "country", "city", "grab_service", "gross_sales_vnd",
        "net_sales_vnd", "transaction_count", "avg_transaction_amount_vnd",
        "average_rating",
    ),
    "menu_sales": (
        "date", "country", "city", "grab_service", "item_name", "units_sold",
        "item_gross_sales_vnd",
    ),
    "offers": (
        "date", "country", "city", "grab_service", "offer_name",
        "gross_sales_vnd", "net_sales_vnd", "transaction_count", "spend_vnd",
    ),
    "peak_hours": (
        "date", "country", "city", "grab_service", "hour", "transaction_count",
    ),
    "product_scoring": (
        "product_name_current", "product_group", "price_segment", "current_price",
        "duplicate_name", "duplicate_with_price_diff", "desc_missing_any",
        "desc_long_any", "photo_count_min", "sku_present_any", "barcode_present_any",
        "gross_revenue", "units_sold", "selling_days", "recorded_sales", "abc",
        "xyz", "abc_xyz", "cell_recorded_sales_rate", "cell_active_products",
        "review_priority_score", "priority_label", "managerial_class",
    ),
    "miwi_item_breakdown": (
        "date", "item_name", "modifiers_components", "missing_reported",
        "wrong_reported", "total_reported",
    ),
    "miwi_heatmap": ("disposition", "date", "hour", "order_time_local"),
    "customer_reviews": (
        "service_type", "rating", "type", "review_datetime", "review_date",
        "has_reply", "has_review_text", "review_length", "rating_group",
        "reported_wilted", "reported_missing_wrong", "reported_quality_positive",
        "reported_delivery",
    ),
}

TABLES = tuple(SAFE_COLUMNS)


@dataclass(frozen=True)
class DataBundle:
    tables: Dict[str, pd.DataFrame]
    source: str

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]


def _client() -> tuple[bigquery.Client, str, str]:
    project = st.secrets.get("project_id", "plasma-renderer-507213-p8")
    dataset = st.secrets.get("dataset_id", "grabmart_business")
    account = st.secrets.get("gcp_service_account")
    if account:
        credentials = service_account.Credentials.from_service_account_info(dict(account))
        return bigquery.Client(project=project, credentials=credentials), project, dataset
    raise RuntimeError(
        "Chưa cấu hình gcp_service_account trong Streamlit secrets; "
        "ứng dụng sẽ sử dụng dữ liệu demo an toàn."
    )


@st.cache_data(ttl=900, show_spinner="Đang đọc dữ liệu từ BigQuery...")
def load_bigquery() -> DataBundle:
    client, project, dataset = _client()
    frames = {}
    for name, columns in SAFE_COLUMNS.items():
        projection = ", ".join(f"`{column}`" for column in columns)
        query = f"SELECT {projection} FROM `{project}.{dataset}.{name}`"
        frames[name] = client.query(query).to_dataframe()
    return DataBundle(frames, f"BigQuery (các cột an toàn): {project}.{dataset}")


def load_demo() -> DataBundle:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2026-05-25", periods=97)
    sales = pd.DataFrame({
        "date": dates,
        "gross_sales_vnd": rng.integers(1_500_000, 7_000_000, len(dates)),
        "net_sales_vnd": rng.integers(1_300_000, 6_300_000, len(dates)),
        "transaction_count": rng.integers(5, 28, len(dates)),
    })
    n = 994
    gross = np.zeros(n)
    gross[:370] = rng.lognormal(12, 1.2, 370)
    groups = rng.choice(["Hoa nguyên liệu", "Hoa cúng", "Hoa dịp lễ", "Hoa thiết kế"], n)
    priorities = rng.choice(
        ["High review priority", "Medium review priority", "Monitor / improve data", "Core / lower review priority"],
        n, p=[0.45, 0.21, 0.19, 0.15]
    )
    score = pd.DataFrame({
        "product_name_current": [f"Sản phẩm demo {i+1}" for i in range(n)],
        "product_group": groups,
        "price_segment": rng.choice(["<100K", "100–199K", "200–499K", ">=500K"], n),
        "gross_revenue": gross,
        "units_sold": rng.integers(0, 40, n),
        "selling_days": rng.integers(0, 20, n),
        "recorded_sales": gross > 0,
        "abc": np.where(gross == 0, "N_No sales", rng.choice(["A_top80", "B_next15", "C_tail5"], n)),
        "xyz": np.where(gross == 0, "N_no_selling_day", rng.choice(["X_repeated_10plus_days", "Y_occasional_4_9_days", "Z_sporadic_1_3_days"], n)),
        "priority_label": priorities,
        "managerial_class": rng.choice(
            ["Core", "Seasonal", "Growth", "Review / rationalize"], n
        ),
        "review_priority_score": rng.integers(10, 96, n),
        "duplicate_name": rng.random(n) < .07,
        "duplicate_with_price_diff": rng.random(n) < .015,
        "desc_missing_any": rng.random(n) < .19,
        "photo_count_min": rng.integers(1, 5, n),
        "sku_present_any": rng.random(n) > .76,
        "barcode_present_any": rng.random(n) > .77,
    })
    reviews = pd.DataFrame({
        "review_date": pd.date_range("2026-05-31", periods=24, freq="4D"),
        "rating": [1]*7 + [2]*4 + [4]*6 + [5]*7,
        "has_reply": [True]*10 + [False]*14,
        "reported_wilted": [True]*3 + [False]*21,
        "reported_missing_wrong": [False]*20 + [True]*4,
    })
    miwi_items = pd.DataFrame({"missing_reported": [4], "wrong_reported": [10], "total_reported": [14]})
    miwi_heatmap = pd.DataFrame({"disposition": ["Wrong"]*5 + ["Missing"]*2, "hour": [10,10,11,14,16,7,14]})
    peak = pd.DataFrame({"hour": list(range(24)), "transaction_count": rng.integers(0, 220, 24)})
    offers = pd.DataFrame({"spend_vnd": [35_747_000], "date": [dates.max()]})
    menu = pd.DataFrame()
    return DataBundle({
        "sales_daily": sales, "menu_sales": menu, "offers": offers, "peak_hours": peak,
        "product_scoring": score, "miwi_item_breakdown": miwi_items,
        "miwi_heatmap": miwi_heatmap, "customer_reviews": reviews,
    }, "Dữ liệu demo tổng hợp – không chứa dữ liệu cá nhân")


def load_data(use_demo: bool, live_enabled: bool = False) -> DataBundle:
    if use_demo or not live_enabled:
        return load_demo()
    try:
        return load_bigquery()
    except Exception as exc:
        st.warning("Không thể kết nối BigQuery. Ứng dụng chuyển sang dữ liệu demo an toàn.")
        with st.expander("Chi tiết kỹ thuật"):
            st.code(str(exc))
        return load_demo()

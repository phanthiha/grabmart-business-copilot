from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account


TABLES = (
    "sales_daily",
    "menu_sales",
    "offers",
    "peak_hours",
    "product_scoring",
    "miwi_item_breakdown",
    "miwi_heatmap",
    "customer_reviews",
)


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
    frames = {
        name: client.query(f"SELECT * FROM `{project}.{dataset}.{name}`").to_dataframe()
        for name in TABLES
    }
    return DataBundle(frames, f"BigQuery: {project}.{dataset}")


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


def load_data(use_demo: bool) -> DataBundle:
    if use_demo:
        return load_demo()
    try:
        return load_bigquery()
    except Exception as exc:
        st.warning("Không thể kết nối BigQuery. Ứng dụng chuyển sang dữ liệu demo an toàn.")
        with st.expander("Chi tiết kỹ thuật"):
            st.code(str(exc))
        return load_demo()

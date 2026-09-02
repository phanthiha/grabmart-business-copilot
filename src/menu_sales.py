from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import pandas as pd


COLUMNS = ["date", "country", "city", "merchant", "service", "item", "units_sold", "gross_sales_vnd"]
COLUMN_ALIASES = {
    "Date": "date", "Ngày": "date",
    "Country": "country", "Quốc gia": "country",
    "City": "city", "Thành phố": "city",
    "Merchant": "merchant", "Người bán": "merchant",
    "Grab Service": "service", "Dịch vụ Grab": "service",
    "Item": "item", "Sản phẩm": "item",
    "Units Sold": "units_sold", "Số lượng đã bán": "units_sold",
    "Item Gross Sales (₫)": "gross_sales_vnd",
    "Tổng doanh thu của sản phẩm (₫)": "gross_sales_vnd",
}
DEDUP_KEYS = ["date", "merchant", "service", "item", "units_sold", "gross_sales_vnd"]


@dataclass
class MenuSalesResult:
    data: pd.DataFrame
    files: pd.DataFrame
    overlaps: pd.DataFrame


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Không đọc được mã hóa CSV.")


def read_menu_sales(raw: bytes, filename: str) -> pd.DataFrame:
    frame = pd.read_csv(io.StringIO(_decode(raw)), dtype=str, keep_default_na=False)
    frame = frame.rename(columns={column: COLUMN_ALIASES.get(column.strip(), column.strip()) for column in frame.columns})
    missing = set(COLUMNS).difference(frame.columns)
    if missing:
        raise ValueError(f"{filename}: thiếu cột {', '.join(sorted(missing))}")
    frame = frame[COLUMNS].copy()
    frame["date"] = pd.to_datetime(frame["date"], dayfirst=True, errors="coerce")
    frame["units_sold"] = pd.to_numeric(frame["units_sold"], errors="coerce")
    frame["gross_sales_vnd"] = pd.to_numeric(frame["gross_sales_vnd"], errors="coerce")
    invalid = frame[["date", "units_sold", "gross_sales_vnd"]].isna().any(axis=1)
    if invalid.any():
        raise ValueError(f"{filename}: có {int(invalid.sum())} dòng sai ngày, số lượng hoặc doanh thu")
    if frame["item"].astype(str).str.strip().eq("").any():
        raise ValueError(f"{filename}: có sản phẩm trống tên")
    frame["units_sold"] = frame["units_sold"].astype(int)
    frame["gross_sales_vnd"] = frame["gross_sales_vnd"].astype(float)
    frame["source_file"] = filename
    return frame


def combine_menu_sales(files: list[tuple[str, bytes]]) -> MenuSalesResult:
    frames = [read_menu_sales(raw, name) for name, raw in files]
    summaries = []
    for frame in frames:
        summaries.append({
            "Tệp": frame.source_file.iloc[0], "Từ ngày": frame.date.min().date(), "Đến ngày": frame.date.max().date(),
            "Số dòng": len(frame), "Sản phẩm": frame.item.nunique(), "Số lượng": int(frame.units_sold.sum()),
            "Doanh thu": float(frame.gross_sales_vnd.sum()),
        })
    overlap_rows = []
    for left_index in range(len(frames)):
        for right_index in range(left_index + 1, len(frames)):
            left, right = frames[left_index], frames[right_index]
            shared = left.merge(right, on=DEDUP_KEYS, how="inner")
            overlap_rows.append({
                "Tệp 1": left.source_file.iloc[0], "Tệp 2": right.source_file.iloc[0],
                "Dòng trùng khớp": len(shared),
                "Cảnh báo": "Không cộng trực tiếp" if len(shared) else "Không phát hiện trùng",
            })
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["date", "item", "source_file"], ascending=[True, True, True])
    combined = combined.drop_duplicates(DEDUP_KEYS, keep="last").reset_index(drop=True)
    return MenuSalesResult(combined, pd.DataFrame(summaries), pd.DataFrame(overlap_rows))


def product_performance(data: pd.DataFrame) -> pd.DataFrame:
    result = data.groupby("item", as_index=False).agg(
        units_sold=("units_sold", "sum"), gross_sales_vnd=("gross_sales_vnd", "sum"),
        selling_days=("date", "nunique"), first_sale=("date", "min"), last_sale=("date", "max"),
    )
    result["average_selling_price"] = result.gross_sales_vnd / result.units_sold.replace(0, np.nan)
    result["revenue_per_selling_day"] = result.gross_sales_vnd / result.selling_days.replace(0, np.nan)
    result["days_since_last_sale"] = (data.date.max() - result.last_sale).dt.days
    return result.sort_values("gross_sales_vnd", ascending=False)


def period_comparison(data: pd.DataFrame, recent_days: int) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    end = data.date.max()
    recent_start = end - pd.Timedelta(days=recent_days - 1)
    previous_start = recent_start - pd.Timedelta(days=recent_days)
    previous_end = recent_start - pd.Timedelta(days=1)
    labels = [("Kỳ trước", previous_start, previous_end), ("Kỳ gần nhất", recent_start, end)]
    rows = []
    for label, start, finish in labels:
        view = data[data.date.between(start, finish)]
        rows.append({
            "Kỳ": label, "Từ ngày": start.date(), "Đến ngày": finish.date(), "Ngày có dữ liệu": view.date.nunique(),
            "Sản phẩm có bán": view.item.nunique(), "Số lượng": int(view.units_sold.sum()),
            "Doanh thu": float(view.gross_sales_vnd.sum()),
        })
    output = pd.DataFrame(rows)
    return output, recent_start, end


def preparation_board(data: pd.DataFrame, windows: tuple[int, ...] = (7, 14, 30)) -> pd.DataFrame:
    end = data.date.max()
    base = product_performance(data)[["item", "gross_sales_vnd", "selling_days", "last_sale"]].copy()
    for days in windows:
        view = data[data.date.between(end - pd.Timedelta(days=days - 1), end)]
        units = view.groupby("item").units_sold.sum()
        active = view.groupby("item").date.nunique()
        base[f"units_{days}d"] = base.item.map(units).fillna(0).astype(int)
        base[f"selling_days_{days}d"] = base.item.map(active).fillna(0).astype(int)
    base["Gợi ý chuẩn bị"] = np.select(
        [base.units_7d.ge(7), base.units_14d.ge(5), base.units_30d.gt(0)],
        ["Chuẩn bị thường xuyên", "Dự phòng nguyên liệu", "Chỉ chuẩn bị khi có đơn"],
        default="Mẫu chưa bán gần đây",
    )
    return base.sort_values(["units_7d", "units_30d", "gross_sales_vnd"], ascending=False)


def price_changes(data: pd.DataFrame) -> pd.DataFrame:
    daily = data.groupby(["item", "date"], as_index=False).agg(units=("units_sold", "sum"), revenue=("gross_sales_vnd", "sum"))
    daily["unit_price"] = daily.revenue / daily.units.replace(0, np.nan)
    result = daily.groupby("item", as_index=False).agg(
        price_levels=("unit_price", "nunique"), minimum_price=("unit_price", "min"),
        maximum_price=("unit_price", "max"), latest_price=("unit_price", "last"),
    )
    result["price_range"] = result.maximum_price - result.minimum_price
    return result[result.price_levels.gt(1)].sort_values("price_range", ascending=False)

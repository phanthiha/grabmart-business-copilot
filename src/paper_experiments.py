from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import chi2_contingency, rankdata


def gini(values) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    x = x[np.isfinite(x)]
    if len(x) == 0 or x.sum() <= 0:
        return 0.0
    ranks = np.arange(1, len(x) + 1)
    return float(2 * np.sum(ranks * x) / (len(x) * x.sum()) - (len(x) + 1) / len(x))


def concentration(score: pd.DataFrame) -> pd.DataFrame:
    sold = score.loc[score.recorded_sales.astype(bool)].sort_values("gross_revenue", ascending=False)
    active_n = len(score)
    sold_n = len(sold)
    revenue = sold.gross_revenue.sum()
    cumulative = sold.gross_revenue.cumsum() / revenue if revenue else pd.Series(dtype=float)
    n80 = int((cumulative < 0.8).sum() + 1) if sold_n else 0
    top20_n = max(1, int(np.ceil(sold_n * 0.2))) if sold_n else 0
    rows = [
        ["Sản phẩm đang hoạt động", active_n, "sản phẩm"],
        ["Sản phẩm có ghi nhận bán", sold_n, f"{sold_n / active_n:.1%}" if active_n else "0%"],
        ["Sản phẩm chưa ghi nhận bán", active_n - sold_n, f"{(active_n - sold_n) / active_n:.1%}" if active_n else "0%"],
        ["Top 20% sản phẩm: tỷ trọng doanh thu", float(sold.head(top20_n).gross_revenue.sum() / revenue) if revenue else 0, "tỷ lệ"],
        ["Sản phẩm cần để đạt 80% doanh thu", n80, f"{n80 / sold_n:.1%} sản phẩm đã bán" if sold_n else "0%"],
        ["Gini trong nhóm đã bán", gini(sold.gross_revenue), "hệ số"],
        ["Gini toàn danh mục gồm doanh thu 0", gini(score.gross_revenue), "hệ số"],
    ]
    return pd.DataFrame(rows, columns=["Chỉ tiêu", "Giá trị", "Diễn giải"])


def frequency_bands(score: pd.DataFrame) -> pd.DataFrame:
    sold = score.loc[score.recorded_sales.astype(bool)].copy()
    sold["Dải ngày bán"] = pd.cut(
        sold.selling_days,
        bins=[0, 1, 3, 9, np.inf],
        labels=["1 ngày", "2–3 ngày", "4–9 ngày", ">=10 ngày"],
    )
    out = sold.groupby("Dải ngày bán", observed=False).agg(
        Sản_phẩm=("product_name_current", "size"),
        Số_lượng=("units_sold", "sum"),
        Doanh_thu=("gross_revenue", "sum"),
    ).reset_index()
    out["Tỷ trọng sản phẩm"] = out.Sản_phẩm / out.Sản_phẩm.sum()
    out["Tỷ trọng số lượng"] = out.Số_lượng / out.Số_lượng.sum()
    out["Tỷ trọng doanh thu"] = out.Doanh_thu / out.Doanh_thu.sum()
    return out


def assortment_performance(score: pd.DataFrame, dimension: str) -> pd.DataFrame:
    total_products = len(score)
    total_revenue = score.gross_revenue.sum()
    out = score.groupby(dimension, dropna=False).agg(
        active_products=("product_name_current", "size"),
        products_with_sales=("recorded_sales", "sum"),
        gross_revenue=("gross_revenue", "sum"),
        units_sold=("units_sold", "sum"),
    ).reset_index()
    out["recorded_sales_rate"] = out.products_with_sales / out.active_products
    out["active_product_share"] = out.active_products / total_products
    out["revenue_share"] = out.gross_revenue / total_revenue if total_revenue else 0
    out["revenue_productivity"] = out.revenue_share / out.active_product_share
    return out.sort_values("revenue_productivity", ascending=False)


def cramer_test(score: pd.DataFrame, factor: str) -> dict:
    table = pd.crosstab(score[factor].fillna("Không xác định"), score.recorded_sales.astype(bool))
    chi2, p_value, dof, expected = chi2_contingency(table, correction=False)
    n = table.to_numpy().sum()
    denominator = min(table.shape[0] - 1, table.shape[1] - 1)
    v = np.sqrt(chi2 / (n * denominator)) if n and denominator > 0 else 0.0
    return {
        "Yếu tố": factor,
        "Chi-square": float(chi2),
        "Bậc tự do": int(dof),
        "p-value": float(p_value),
        "Cramér's V": float(v),
        "Ô có tần suất kỳ vọng < 5": int((expected < 5).sum()),
    }


def duplicate_test(score: pd.DataFrame) -> dict:
    return cramer_test(score.assign(duplicate_name=score.duplicate_name.astype(bool)), "duplicate_name")


def quality_summary(score: pd.DataFrame) -> pd.DataFrame:
    values = [
        ["Tên sản phẩm trùng", int(score.duplicate_name.sum())],
        ["Tên trùng nhưng khác giá", int(score.duplicate_with_price_diff.sum())],
        ["Thiếu mô tả", int(score.desc_missing_any.sum())],
        ["Chỉ có một ảnh", int(score.photo_count_min.eq(1).sum())],
        ["Có SKU nội bộ", int(score.sku_present_any.sum())],
        ["Có barcode", int(score.barcode_present_any.sum())],
    ]
    out = pd.DataFrame(values, columns=["Chỉ tiêu", "Số sản phẩm"])
    out["Tỷ lệ"] = out["Số sản phẩm"] / len(score) if len(score) else 0
    return out


def sensitivity(score: pd.DataFrame) -> pd.DataFrame:
    sold = score.loc[score.recorded_sales.astype(bool)]
    total_revenue = sold.gross_revenue.sum()
    rows = []
    for label, mask in [
        ["<=1 ngày", sold.selling_days.le(1)],
        ["<=2 ngày", sold.selling_days.le(2)],
        ["<=3 ngày", sold.selling_days.le(3)],
        [">=10 ngày", sold.selling_days.ge(10)],
        [">=20 ngày", sold.selling_days.ge(20)],
    ]:
        rows.append([label, int(mask.sum()), float(mask.mean()), float(sold.loc[mask, "gross_revenue"].sum() / total_revenue) if total_revenue else 0])
    return pd.DataFrame(rows, columns=["Ngưỡng ngày bán", "Sản phẩm", "Tỷ trọng sản phẩm đã bán", "Tỷ trọng doanh thu"])


def promotion_summary(offers: pd.DataFrame, sales: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    gross = float(sales.gross_sales_vnd.sum())
    spend = float(offers.spend_vnd.sum())
    offer_gross = float(offers.gross_sales_vnd.sum())
    summary = pd.DataFrame([
        ["Ngày quan sát", int(pd.to_datetime(sales.date).nunique())],
        ["Ngày có khuyến mãi", int(pd.to_datetime(offers.date).nunique())],
        ["Số nhãn chương trình", int(offers.offer_name.nunique())],
        ["Tổng chi khuyến mãi (VND)", spend],
        ["Chi khuyến mãi / doanh thu gộp", spend / gross if gross else 0],
        ["Doanh thu gán cho offer / doanh thu thực", offer_gross / gross if gross else 0],
    ], columns=["Chỉ tiêu", "Giá trị"])
    by_offer = offers.groupby("offer_name", as_index=False).agg(
        days=("date", "nunique"),
        gross_sales_vnd=("gross_sales_vnd", "sum"),
        transaction_count=("transaction_count", "sum"),
        spend_vnd=("spend_vnd", "sum"),
    ).sort_values("spend_vnd", ascending=False)
    by_offer["spend_rate"] = by_offer.spend_vnd / by_offer.gross_sales_vnd.replace(0, np.nan)
    return summary, by_offer


def _auc(y: np.ndarray, score: np.ndarray) -> float:
    positives = y.sum()
    negatives = len(y) - positives
    if positives == 0 or negatives == 0:
        return np.nan
    return float((rankdata(score)[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def _average_precision(y: np.ndarray, score: np.ndarray) -> float:
    order = np.argsort(-score)
    ranked_y = y[order]
    positives = ranked_y.sum()
    if positives == 0:
        return np.nan
    precision = np.cumsum(ranked_y) / np.arange(1, len(ranked_y) + 1)
    return float((precision * ranked_y).sum() / positives)


def logistic_cross_validation(score: pd.DataFrame, folds: int = 5, seed: int = 42) -> pd.DataFrame:
    categorical = pd.get_dummies(score[["product_group", "price_segment"]].fillna("Không xác định"), drop_first=True, dtype=float)
    quality = pd.DataFrame({
        "duplicate_name": score.duplicate_name.astype(float),
        "duplicate_with_price_diff": score.duplicate_with_price_diff.astype(float),
        "desc_missing": score.desc_missing_any.astype(float),
        "one_photo": score.photo_count_min.eq(1).astype(float),
        "missing_sku": (~score.sku_present_any.astype(bool)).astype(float),
        "missing_barcode": (~score.barcode_present_any.astype(bool)).astype(float),
    })
    x = np.column_stack([np.ones(len(score)), categorical.to_numpy(), quality.to_numpy()])
    y = score.recorded_sales.astype(int).to_numpy()
    rng = np.random.default_rng(seed)
    fold_id = np.empty(len(y), dtype=int)
    for cls in [0, 1]:
        idx = np.flatnonzero(y == cls)
        rng.shuffle(idx)
        fold_id[idx] = np.arange(len(idx)) % folds
    rows = []
    for fold in range(folds):
        train = fold_id != fold
        test = ~train

        def objective(beta):
            p = np.clip(expit(x[train] @ beta), 1e-9, 1 - 1e-9)
            loss = -(y[train] * np.log(p) + (1 - y[train]) * np.log(1 - p)).sum()
            penalty = 0.5 * np.square(beta[1:]).sum()
            return loss + penalty

        fit = minimize(objective, np.zeros(x.shape[1]), method="L-BFGS-B")
        probability = expit(x[test] @ fit.x)
        rows.append([fold + 1, int(test.sum()), _auc(y[test], probability), _average_precision(y[test], probability), bool(fit.success)])
    result = pd.DataFrame(rows, columns=["Fold", "Số quan sát", "AUC", "Average precision", "Hội tụ"])
    result.loc[len(result)] = ["Trung bình", int(result["Số quan sát"].sum()), result.AUC.mean(), result["Average precision"].mean(), result["Hội tụ"].all()]
    return result


def operational_extension(miwi: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    rating = pd.to_numeric(reviews.rating, errors="coerce")
    low = rating.le(2)
    return pd.DataFrame([
        ["Sự cố MIWI được báo cáo", int(miwi.total_reported.sum()), "Mô tả, không suy luận"],
        ["Đánh giá khách hàng", int(len(reviews)), "Mẫu nhỏ"],
        ["Điểm đánh giá trung bình", float(rating.mean()), "Thang điểm 1–5"],
        ["Tỷ lệ đánh giá 4–5 sao", float(rating.ge(4).mean()), "Tỷ lệ"],
        ["Tỷ lệ phản hồi đánh giá thấp", float(reviews.loc[low, "has_reply"].mean()) if low.any() else np.nan, "Tỷ lệ"],
    ], columns=["Chỉ tiêu", "Giá trị", "Lưu ý"])

from __future__ import annotations

import numpy as np
import pandas as pd


def gini(values) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return 0.0
    ranks = np.arange(1, len(x) + 1)
    return float(2 * np.sum(ranks * x) / (len(x) * x.sum()) - (len(x) + 1) / len(x))


def catalogue_issues(score: pd.DataFrame) -> pd.DataFrame:
    values = {
        "Trùng tên": int(score["duplicate_name"].sum()),
        "Trùng tên nhưng khác giá": int(score["duplicate_with_price_diff"].sum()),
        "Thiếu mô tả": int(score["desc_missing_any"].sum()),
        "Mô tả quá dài": int(score.get("desc_long_any", pd.Series(False, index=score.index)).astype(bool).sum()),
        "Không có ảnh mẫu": int(score["photo_count_min"].eq(0).sum()),
        "Chỉ có một ảnh": int(score["photo_count_min"].eq(1).sum()),
        "Barcode đã nhập cần xác minh": int(score["barcode_present_any"].astype(bool).sum()),
    }
    return pd.DataFrame({"Vấn đề": values.keys(), "Số sản phẩm": values.values()})


def action_list(score: pd.DataFrame, reviews: pd.DataFrame, miwi: pd.DataFrame) -> pd.DataFrame:
    high = int(score.priority_label.eq("High review priority").sum())
    low_reply = float(reviews.loc[pd.to_numeric(reviews.rating).le(2), "has_reply"].mean()) if len(reviews) else 0
    wrong = int(miwi.get("wrong_reported", pd.Series(dtype=int)).sum())
    missing_description = int(score.desc_missing_any.astype(bool).sum())
    rows = [
        ["ACT-01", "Cao", f"Rà soát {high} sản phẩm ưu tiên cao", "Điểm ưu tiên tổng hợp", "Danh mục/Menu", "Chưa thực hiện"],
        ["ACT-02", "Cao", f"Kiểm tra quy trình chuẩn bị {wrong} lượt giao sai", "MIWI Wrong", "Đơn hàng/Vận hành", "Chưa thực hiện"],
        ["ACT-03", "Trung bình", f"Bổ sung mô tả quy cách cho {missing_description} sản phẩm", "Kiểm toán catalogue", "Danh mục/Menu", "Chưa thực hiện"],
        ["ACT-04", "Trung bình", f"Nâng tỷ lệ trả lời đánh giá thấp, hiện {low_reply:.1%}", "Customer Review", "Đánh giá khách hàng", "Chưa thực hiện"],
        ["ACT-05", "Theo dõi", "Xác nhận vai trò mùa vụ của sản phẩm A–Z", "ABC–XYZ", "Danh mục/Menu", "Chưa thực hiện"],
    ]
    return pd.DataFrame(rows, columns=["Mã", "Mức độ", "Công việc đề xuất", "Căn cứ dữ liệu", "Khu vực GrabMerchant", "Trạng thái"])

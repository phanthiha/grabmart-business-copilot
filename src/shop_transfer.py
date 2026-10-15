from __future__ import annotations

import io
import re
import zipfile

import pandas as pd

from src.grab_catalogue import GrabMenuPackage


def target_template_identity(raw: bytes) -> tuple[str, list[str]]:
    """Đọc mã shop từ tên gói/mẫu tạo món và danh mục hợp lệ của shop đích."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            root_csv = [name for name in names if name.lower().endswith(".csv") and "/" not in name.replace("\\", "/")]
            if len(root_csv) != 1:
                raise ValueError("ZIP shop đích phải có đúng một CSV ở cấp đầu tiên.")
            csv_name = root_csv[0]
            template = pd.read_csv(archive.open(csv_name), dtype=str, keep_default_na=False)
            if "*ItemID" in template.columns:
                raise ValueError(
                    "ZIP shop đích là gói Chỉnh sửa món. Hãy vào GrabMerchant của shop đích và tải mẫu Tạo món hàng loạt."
                )
            if "_itemid" in csv_name.casefold():
                raise ValueError("Hãy dùng mẫu Tạo món hàng loạt của shop đích, không dùng báo cáo lỗi.")
            store_match = re.search(r"(?:^|_)(5-[A-Z0-9]+)(?:_|\.)", csv_name, flags=re.IGNORECASE)
            if not store_match:
                store_match = next((match for name in names if (
                    match := re.search(r"(?:^|/)(5-[A-Z0-9]+)(?:_|\.)", name, flags=re.IGNORECASE)
                )), None)
            store_id = store_match.group(1).upper() if store_match else "Không xác định từ tên mẫu"
            department_name = next(
                (name for name in names if name.replace("\\", "/").lower() == "resources/department_list.csv"),
                None,
            )
            if department_name is None:
                raise ValueError("Mẫu shop đích thiếu resources/department_list.csv.")
            departments = pd.read_csv(archive.open(department_name), dtype=str, keep_default_na=False)
    except zipfile.BadZipFile as exc:
        raise ValueError("ZIP shop đích không hợp lệ.") from exc
    if "sub-department" not in departments.columns:
        raise ValueError("Danh sách danh mục shop đích thiếu cột sub-department.")
    categories = sorted(
        {value.strip() for value in departments["sub-department"].astype(str) if value.strip()},
        key=str.casefold,
    )
    return store_id, categories


def source_image_assets(package: GrabMenuPackage) -> tuple[dict[str, bytes], dict[str, str]]:
    """Lấy ảnh thực sự nằm trong ZIP nguồn; không tái sử dụng URL CMS gắn với ItemID cũ."""
    assets: dict[str, bytes] = {}
    aliases: dict[str, str] = {}
    for member, content in package.members.items():
        normalized = member.replace("\\", "/")
        if not normalized.lower().startswith("images/"):
            continue
        filename = normalized.rsplit("/", 1)[-1]
        if filename.casefold() == "example_photo.jpg":
            continue
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
        if re.fullmatch(r"[A-Za-z0-9_-]+\.(?:jpg|png)", safe_name, flags=re.IGNORECASE):
            assets[safe_name] = content
            aliases[filename] = safe_name
            aliases[normalized] = safe_name
    return assets, aliases


def transfer_review(package: GrabMenuPackage, item_ids: list[str], target_categories: list[str]) -> pd.DataFrame:
    selected = package.products.loc[package.products["*ItemID"].astype(str).isin(item_ids)].copy()
    if selected.empty:
        return pd.DataFrame()
    valid_categories = set(target_categories)
    fallback = target_categories[0] if target_categories else ""
    rows: list[dict[str, object]] = []
    _, aliases = source_image_assets(package)
    option_columns = [column for column in selected.columns if column.startswith("OptionGroup")]
    for _, source in selected.iterrows():
        source_category = str(source.get("*GrabCategoryName", "")).strip()
        row: dict[str, object] = {
            "Chọn tạo": True,
            "ItemID nguồn": str(source.get("*ItemID", "")),
            "Tên sản phẩm": str(source.get("*ItemName", ""))[:80],
            "Giá bán (₫)": int(float(str(source.get("*Price", "0")) or 0)),
            "Danh mục nguồn": source_category,
            "Danh mục Grab": source_category if source_category in valid_categories else fallback,
            "Mô tả": str(source.get("Description", ""))[:300],
            "Tình trạng tên": "Đã xác minh",
        }
        for slot in range(1, 5):
            source_photo = str(source.get(f"Photo{slot}", "")).strip()
            row[f"Tên file ảnh {slot}"] = aliases.get(source_photo, aliases.get(source_photo.rsplit("/", 1)[-1], ""))
        for column in option_columns:
            row[column] = str(source.get(column, ""))
        rows.append(row)
    return pd.DataFrame(rows)

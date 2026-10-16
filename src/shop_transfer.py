from __future__ import annotations

import io
import re
import urllib.parse
import urllib.request
import zipfile

import pandas as pd
from PIL import Image, UnidentifiedImageError

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


def download_grab_image_assets(
    package: GrabMenuPackage,
    item_ids: list[str],
    max_total_bytes: int = 150 * 1024 * 1024,
) -> tuple[dict[str, bytes], dict[str, str], list[str]]:
    """Tải ảnh công khai từ CDN Grab, xác thực nội dung và chuyển thành JPEG cho ZIP tạo món."""
    allowed_hosts = {"huawei-food-cms.grab.com", "food-cms.grab.com"}
    chosen = package.products.loc[package.products["*ItemID"].astype(str).isin(item_ids)]
    assets, aliases = source_image_assets(package)
    warnings: list[str] = []
    total = sum(len(content) for content in assets.values())
    for _, product in chosen.iterrows():
        item_id = re.sub(r"[^A-Za-z0-9_-]+", "_", str(product.get("*ItemID", "item")))
        for slot in range(1, 5):
            source = str(product.get(f"Photo{slot}", "")).strip()
            if not source or source in aliases:
                continue
            parsed = urllib.parse.urlparse(source)
            if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
                warnings.append(f"{item_id} Photo{slot}: bỏ qua URL không thuộc CDN ảnh Grab")
                continue
            try:
                request = urllib.request.Request(source, headers={"User-Agent": "GrabMart-Catalogue-Transfer/1.0"})
                with urllib.request.urlopen(request, timeout=20) as response:
                    raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise ValueError("ảnh nguồn vượt 8 MB")
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
                    if image.width < 100 or image.height < 100:
                        raise ValueError("kích thước ảnh quá nhỏ")
                    converted = image.convert("RGB")
                    converted.thumbnail((2000, 2000))
                    output = io.BytesIO()
                    quality = 90
                    while True:
                        output.seek(0)
                        output.truncate(0)
                        converted.save(output, format="JPEG", quality=quality, optimize=True)
                        if output.tell() <= 2 * 1024 * 1024 or quality <= 60:
                            break
                        quality -= 10
                    content = output.getvalue()
                if len(content) > 2 * 1024 * 1024:
                    raise ValueError("không thể nén ảnh xuống dưới 2 MB")
                if total + len(content) > max_total_bytes:
                    raise ValueError("tổng ảnh đã đạt giới hạn 150 MB")
                filename = f"{item_id}_{slot}.jpg"
                assets[filename] = content
                aliases[source] = filename
                total += len(content)
            except (OSError, ValueError, UnidentifiedImageError) as exc:
                warnings.append(f"{item_id} Photo{slot}: {exc}")
    return assets, aliases, warnings


def transfer_review(
    package: GrabMenuPackage,
    item_ids: list[str],
    target_categories: list[str],
    image_aliases: dict[str, str] | None = None,
    category_mapping: dict[str, str] | None = None,
) -> pd.DataFrame:
    selected = package.products.loc[package.products["*ItemID"].astype(str).isin(item_ids)].copy()
    if selected.empty:
        return pd.DataFrame()
    valid_categories = set(target_categories)
    category_mapping = category_mapping or {}
    rows: list[dict[str, object]] = []
    _, local_aliases = source_image_assets(package)
    aliases = {**local_aliases, **(image_aliases or {})}
    option_columns = [column for column in selected.columns if column.startswith("OptionGroup")]
    for _, source in selected.iterrows():
        source_category = str(source.get("*GrabCategoryName", "")).strip()
        row: dict[str, object] = {
            "Chọn tạo": True,
            "ItemID nguồn": str(source.get("*ItemID", "")),
            "Tên sản phẩm": str(source.get("*ItemName", ""))[:80],
            "Giá bán (₫)": int(float(str(source.get("*Price", "0")) or 0)),
            "Danh mục nguồn": source_category,
            "Danh mục Grab": (
                source_category if source_category in valid_categories else category_mapping.get(source_category, "")
            ),
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

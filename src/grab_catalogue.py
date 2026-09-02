from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass

import pandas as pd


ITEM_ID = "*ItemID"
STORE_ID = "StoreID"
EDITABLE_FIELDS = {
    "ProposedItemName": "*ItemName",
    "ProposedPrice": "*Price",
    "ProposedCategory": "*GrabCategoryName",
    "ProposedStatus": "*AvailableStatus",
    "ProposedDescription": "Description",
}
VALID_ACTIONS = {"KEEP", "UPDATE", "HIDE", "DISCONTINUE", "REVIEW"}
VALID_STATUSES = {"AVAILABLE", "UNAVAILABLE_TODAY", "UNAVAILABLE_PERMANENTLY", "HIDDEN"}


@dataclass
class GrabMenuPackage:
    members: dict[str, bytes]
    csv_name: str
    catalogue: pd.DataFrame
    departments: set[str]

    @property
    def products(self) -> pd.DataFrame:
        # Dòng dữ liệu đầu tiên là hướng dẫn chính thức của Grab.
        return self.catalogue.iloc[1:].copy()


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Không đọc được mã hóa của CSV trong gói Grab.")


def read_grab_zip(raw: bytes) -> GrabMenuPackage:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if archive.testzip() is not None:
                raise ValueError("Tệp ZIP bị lỗi hoặc chưa tải hoàn chỉnh.")
            unsafe = [n for n in archive.namelist() if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/")]
            if unsafe:
                raise ValueError("ZIP chứa đường dẫn không an toàn.")
            members = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    except zipfile.BadZipFile as exc:
        raise ValueError("Tệp tải lên không phải ZIP hợp lệ.") from exc

    root_csv = [name for name in members if name.lower().endswith(".csv") and "/" not in name.replace("\\", "/")]
    if len(root_csv) != 1:
        raise ValueError("Gói Grab phải có đúng một CSV thực đơn ở cấp đầu tiên của ZIP.")
    csv_name = root_csv[0]
    catalogue = pd.read_csv(io.StringIO(_decode_csv(members[csv_name])), dtype=str, keep_default_na=False)
    required = {ITEM_ID, "*ItemName", "*Price", "*GrabCategoryName", "*AvailableStatus", STORE_ID}
    missing = required.difference(catalogue.columns)
    if missing:
        raise ValueError("CSV thiếu cột bắt buộc: " + ", ".join(sorted(missing)))
    if len(catalogue) < 2:
        raise ValueError("CSV không có dòng hướng dẫn và dữ liệu sản phẩm.")

    departments: set[str] = set()
    department_name = next((n for n in members if n.replace("\\", "/").lower() == "resources/department_list.csv"), None)
    if department_name:
        department_frame = pd.read_csv(io.StringIO(_decode_csv(members[department_name])), dtype=str, keep_default_na=False)
        for column in department_frame.columns:
            departments.update(department_frame[column].astype(str).str.strip().loc[lambda s: s.ne("")])
    return GrabMenuPackage(members, csv_name, catalogue, departments)


def _normal_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    return re.sub(r"\s+", " ", text)


def catalogue_audit(products: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    names = products["*ItemName"].map(_normal_name)
    duplicate = names.ne("") & names.duplicated(keep=False)
    price_count = products.assign(_name=names).groupby("_name")["*Price"].transform("nunique")
    descriptions = products["Description"].astype(str)
    photo_cols = [column for column in ("Photo1", "Photo2", "Photo3", "Photo4") if column in products]
    photo_count = products[photo_cols].apply(lambda row: row.astype(str).str.strip().ne("").sum(), axis=1)
    masks = {
        "Trùng tên": duplicate,
        "Trùng tên nhưng khác giá": duplicate & price_count.gt(1),
        "Thiếu mô tả": descriptions.str.strip().eq(""),
        "Mô tả quá 300 ký tự": descriptions.str.len().gt(300),
        "Chỉ có một ảnh": photo_count.eq(1),
        "Thiếu SKU": products["SKUNumber"].astype(str).str.strip().eq(""),
        "Thiếu barcode": products["BarcodeNumber"].astype(str).str.strip().eq(""),
        "Trạng thái cần rà soát": ~products["*AvailableStatus"].isin(VALID_STATUSES),
    }
    summary = pd.DataFrame({"Vấn đề": masks.keys(), "Số sản phẩm": [int(mask.sum()) for mask in masks.values()]})
    return summary, masks


def make_review_sheet(products: pd.DataFrame, mask: pd.Series, issue: str) -> pd.DataFrame:
    selected = products.loc[mask].copy()
    normalized = selected["*ItemName"].map(_normal_name)
    group_codes = pd.factorize(normalized)[0] + 1
    return pd.DataFrame({
        "Action": "REVIEW",
        "ItemID": selected[ITEM_ID].values,
        "Issue": issue,
        "DuplicateGroup": [f"DUP-{number:03d}" if issue.startswith("Trùng tên") else "" for number in group_codes],
        "CurrentItemName": selected["*ItemName"].values,
        "ProposedItemName": selected["*ItemName"].values,
        "CurrentPrice": selected["*Price"].values,
        "ProposedPrice": selected["*Price"].values,
        "CurrentCategory": selected["*GrabCategoryName"].values,
        "ProposedCategory": selected["*GrabCategoryName"].values,
        "CurrentStatus": selected["*AvailableStatus"].values,
        "ProposedStatus": selected["*AvailableStatus"].values,
        "CurrentDescription": selected["Description"].values,
        "ProposedDescription": selected["Description"].values,
        "ReviewNote": "",
        "StoreID": selected[STORE_ID].values,
    })


def read_review_csv(raw: bytes) -> pd.DataFrame:
    review = pd.read_csv(io.StringIO(_decode_csv(raw)), dtype=str, keep_default_na=False)
    required = {"ItemID", "StoreID", "Action", *EDITABLE_FIELDS}
    missing = required.difference(review.columns)
    if missing:
        raise ValueError("Phiếu xử lý thiếu cột: " + ", ".join(sorted(missing)))
    return review


def validate_review(package: GrabMenuPackage, review: pd.DataFrame) -> pd.DataFrame:
    products = package.products.set_index(ITEM_ID, drop=False)
    errors: list[dict[str, str | int]] = []
    for row_number, row in review.iterrows():
        line = row_number + 2
        item_id = row["ItemID"].strip()
        action = row["Action"].strip().upper()
        if not item_id or item_id not in products.index:
            errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": "ItemID không tồn tại trong gói ZIP gốc"})
            continue
        original = products.loc[item_id]
        if isinstance(original, pd.DataFrame):
            errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": "ItemID bị trùng trong catalogue gốc"})
            continue
        if row["StoreID"].strip() != str(original[STORE_ID]).strip():
            errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": "Không được thay đổi StoreID"})
        if action not in VALID_ACTIONS:
            errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": f"Action không hợp lệ: {action}"})
        if action == "UPDATE":
            if not row["ProposedItemName"].strip() or len(row["ProposedItemName"].strip()) > 80:
                errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": "Tên mới phải có 1–80 ký tự"})
            price = row["ProposedPrice"].strip()
            try:
                if float(price) <= 0:
                    raise ValueError
            except ValueError:
                errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": "Giá mới phải là số dương, không kèm ký hiệu tiền tệ"})
            if len(row["ProposedDescription"]) > 300:
                errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": "Mô tả mới vượt quá 300 ký tự"})
            if package.departments and row["ProposedCategory"].strip() not in package.departments:
                errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": "Danh mục mới không có trong resources/department_list.csv"})
            if row["ProposedStatus"].strip() not in VALID_STATUSES:
                errors.append({"Dòng": line, "ItemID": item_id, "Lỗi": "Trạng thái mới không hợp lệ"})
    duplicated = review["ItemID"].astype(str).str.strip().duplicated(keep=False)
    for _, row in review.loc[duplicated].iterrows():
        errors.append({"Dòng": 0, "ItemID": row["ItemID"], "Lỗi": "ItemID xuất hiện nhiều lần trong phiếu xử lý"})
    return pd.DataFrame(errors, columns=["Dòng", "ItemID", "Lỗi"])


def apply_review(package: GrabMenuPackage, review: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    updated = package.catalogue.copy()
    index_by_id = {str(value): idx for idx, value in updated[ITEM_ID].items() if idx > 0}
    log: list[dict[str, str]] = []
    for _, row in review.iterrows():
        action = row["Action"].strip().upper()
        if action in {"KEEP", "REVIEW"}:
            continue
        item_id = row["ItemID"].strip()
        idx = index_by_id[item_id]
        changes: dict[str, str] = {}
        if action == "UPDATE":
            for proposed, target in EDITABLE_FIELDS.items():
                new_value = row[proposed].strip()
                old_value = str(updated.at[idx, target])
                if new_value != old_value:
                    changes[target] = new_value
        elif action == "HIDE":
            changes["*AvailableStatus"] = "HIDDEN"
        elif action == "DISCONTINUE":
            changes["*AvailableStatus"] = "UNAVAILABLE_PERMANENTLY"
        for field, new_value in changes.items():
            old_value = str(updated.at[idx, field])
            updated.at[idx, field] = new_value
            log.append({"ItemID": item_id, "Trường": field, "Giá trị cũ": old_value, "Giá trị mới": new_value, "Action": action})
    return updated, pd.DataFrame(log, columns=["ItemID", "Trường", "Giá trị cũ", "Giá trị mới", "Action"])


def build_grab_zip(package: GrabMenuPackage, updated: pd.DataFrame) -> bytes:
    members = dict(package.members)
    members[package.csv_name] = updated.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()

from __future__ import annotations

import io
import urllib.parse
import zipfile

import pandas as pd


# Các tên đã đọc tương đối rõ từ bảng giá. Dòng còn mơ hồ được giữ ở trạng thái
# Cần xác minh và không được chọn mặc định để tránh tạo sai sản phẩm.
RAW_ITEMS = [
    ("Hoa bi trắng", 145, True), ("Cỏ tai giác", 60, False), ("Đèn rũ xanh", 110, False),
    ("Hoa tứ giác trắng", 130, False), ("Jasmine lá", 75, True), ("Jasmine hoa", 85, True),
    ("Cành táo gai cam lớn", 115, True), ("Hoa ông lão loại lớn", 160, False),
    ("Hoa ông lão mini", 180, False), ("Delphinium xanh kép", 180, True),
    ("Delphinium xanh", 170, True), ("Delphinium trắng", 220, True), ("Cúc nhí Ý", 105, True),
    ("Sừng hươu vàng", 120, True), ("Sừng hươu cam", 120, True), ("Sừng hươu hồng cam", 110, True),
    ("Lá tuyết mai", 70, True), ("Lá hoàng phụng", 95, False), ("Hoa súp lơ", 110, False),
    ("Hoa Aluna", 125, False), ("Lá bạc Trung Quốc", 115, True), ("Hoa Allium cành", 135, True),
    ("Hoa Allium xoắn", 185, True), ("Hoa hồng chùm cam", 100, True),
    ("Hoa hồng chùm hồng nhạt", 140, True), ("Hoa hồng Sofia", 145, True),
    ("Hoa chiết xạ", 100, False), ("Hoa hồng chùm đỏ", 160, True),
    ("Hoa hồng chùm trắng", 130, True), ("Hoa hồng tuyết", 190, True),
    ("Hoa hồng chùm vàng", 125, True), ("Hoa hồng chùm Plum", 150, True),
    ("Hoa bỉ ngạn", 220, True), ("Tùng rêu", 180, True), ("Hoa lồng đèn", 200, True),
    ("Cành hải châu xanh", 190, True), ("Lá Pitto vàng", 120, True), ("Lá Pitto đỏ", 140, True),
    ("Hoa cát tường hồng", 170, True), ("Hoa phi yến", 95, True),
    ("Hoa mao lương xanh", 95, False), ("Hoa mao lương trắng", 95, False),
    ("Hoa hồng Arosa", 80, False), ("Hoa lay ơn", 115, True), ("Thiên trúc", 145, True),
    ("Hoa cầu gai", 130, True), ("Lá xương cá", 190, True), ("Hoa/cành Ô Long", 150, False),
    ("Cành thiên môn", 135, True), ("Cành tiêu xanh", 100, True), ("Cành tiêu đỏ", 200, True),
    ("Cành tiêu chuông", 150, False), ("Hoa Protea trắng", 200, True),
    ("Hoa Protea hồng", 100, True), ("Hoa Protea cam", 155, True), ("Hoa trà mỹ chùm", 120, True),
    ("Cẩm tú cầu xanh lá", 135, True), ("Cẩm tú cầu trắng", 140, True),
    ("Cẩm tú cầu hồng", 115, True), ("Cẩm tú cầu xanh", 190, True),
    ("Bó cẩm", 140, False), ("Cành táo đầu xanh/đỏ", 180, False), ("Lá cửu hương", 120, False),
    ("Hoa thược dược cam", 80, True), ("Hoa thược dược đen", 160, True),
    ("Hoa Wax xanh lớn", 100, True), ("Cành hồi", 80, True), ("Hoa/cành mâm lược", 250, False),
    ("Cỏ thép", 140, True), ("Hoa thiên nga mắt ngọc", 130, False),
    ("Tulip Nam Phi", 195, True), ("Tulip Nam Phi mini", 160, True),
    ("Dây rối trang trí", 190, True), ("Dây rối hồng", 200, True),
    ("Trái lan lửa", 85, False), ("Cành san hô", 370, True), ("Cành thông đá", 100, True),
    ("Cành quả hạnh phúc", 135, True), ("Hoa cỏ dại", 260, False),
]


def supplier_product_table(multiplier: float = 2.0) -> pd.DataFrame:
    rows = []
    for name, cost_thousand, confirmed in RAW_ITEMS:
        rows.append({
            "Chọn tạo": confirmed,
            "Tên sản phẩm": name,
            "Giá gốc (₫)": int(cost_thousand * 1000),
            "Hệ số giá": float(multiplier),
            "Giá bán (₫)": int(round(cost_thousand * 1000 * multiplier)),
            "Danh mục Grab": "Hoa nguyên liệu / dụng cụ cắm hoa",
            "Mô tả": f"{name} dùng cắm hoa và trang trí. Hình ảnh mang tính minh họa; vui lòng xác nhận mẫu thực tế.",
            "Tên file ảnh": "",
            "Tình trạng tên": "Đã chuẩn hóa" if confirmed else "Cần xác minh với vựa",
            "Tìm ảnh tham chiếu": "https://www.google.com/search?tbm=isch&q=" + urllib.parse.quote_plus(name + " hoa cắt cành"),
        })
    return pd.DataFrame(rows)


def recalculate_prices(frame: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    output = frame.copy()
    output["Giá gốc (₫)"] = pd.to_numeric(output["Giá gốc (₫)"], errors="coerce")
    output["Hệ số giá"] = float(multiplier)
    output["Giá bán (₫)"] = (output["Giá gốc (₫)"] * multiplier).round()
    return output


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError("Không đọc được CSV trong mẫu Grab.")


def build_create_items_zip(template_raw: bytes, products: pd.DataFrame, images: dict[str, bytes]) -> tuple[bytes, list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(template_raw)) as archive:
            unsafe = [n for n in archive.namelist() if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/")]
            if unsafe:
                raise ValueError("Mẫu ZIP chứa đường dẫn không an toàn.")
            members = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    except zipfile.BadZipFile as exc:
        raise ValueError("Mẫu Tạo món hàng loạt không phải ZIP hợp lệ.") from exc
    root_csv = [name for name in members if name.lower().endswith(".csv") and "/" not in name.replace("\\", "/")]
    if len(root_csv) != 1:
        raise ValueError("Mẫu Grab phải có đúng một CSV ở cấp đầu tiên.")
    csv_name = root_csv[0]
    template = pd.read_csv(io.StringIO(_decode(members[csv_name])), dtype=str, keep_default_na=False)
    required = {"*ItemName", "*Price", "*GrabCategoryName"}
    missing = required.difference(template.columns)
    if missing:
        raise ValueError("Mẫu không có các cột tạo món bắt buộc: " + ", ".join(sorted(missing)))
    if "*ItemID" in template.columns:
        raise ValueError("Đây có vẻ là mẫu Chỉnh sửa món vì có cột *ItemID. Hãy tải đúng mẫu Tạo món hàng loạt từ GrabMerchant.")

    selected = products[products["Chọn tạo"].astype(bool)].copy()
    if selected.empty:
        raise ValueError("Chưa chọn sản phẩm nào để tạo.")
    if selected["Tên sản phẩm"].astype(str).str.strip().eq("").any() or selected["Giá bán (₫)"].isna().any():
        raise ValueError("Tên sản phẩm hoặc giá bán chưa hợp lệ.")
    if selected["Tình trạng tên"].eq("Cần xác minh với vựa").any():
        raise ValueError("Còn sản phẩm chưa xác minh tên. Hãy bỏ chọn hoặc xác nhận tên trước.")

    # Giữ dòng hướng dẫn đầu tiên của mẫu nếu có; xóa các dòng ví dụ phía sau.
    instruction = template.iloc[:1].copy()
    rows = []
    missing_images = []
    for _, product in selected.iterrows():
        row = {column: "" for column in template.columns}
        row["*ItemName"] = str(product["Tên sản phẩm"]).strip()
        row["*Price"] = str(int(product["Giá bán (₫)"]))
        row["*GrabCategoryName"] = str(product["Danh mục Grab"]).strip()
        if "AvailabilitySchedule" in row:
            row["AvailabilitySchedule"] = "All opening hours"
        if "*AvailableStatus" in row:
            row["*AvailableStatus"] = "AVAILABLE"
        if "Description" in row:
            row["Description"] = str(product["Mô tả"])[:300]
        if "BarcodeNumber" in row:
            row["BarcodeNumber"] = ""
        if "SKUNumber" in row:
            row["SKUNumber"] = ""
        image_name = str(product["Tên file ảnh"]).strip()
        if "Photo1" in row and image_name:
            if image_name not in images:
                missing_images.append(image_name)
            else:
                row["Photo1"] = image_name
        rows.append(row)
    if missing_images:
        raise ValueError("Thiếu file ảnh đã khai báo: " + ", ".join(sorted(set(missing_images))))
    output_csv = pd.concat([instruction, pd.DataFrame(rows, columns=template.columns)], ignore_index=True)
    members[csv_name] = output_csv.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
    for name, content in images.items():
        members[f"images/{name}"] = content
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue(), selected["Tên sản phẩm"].tolist()

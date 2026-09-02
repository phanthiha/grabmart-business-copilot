from __future__ import annotations

import io
import re
import unicodedata
import urllib.parse
import zipfile

import pandas as pd


# Các tên đã đọc tương đối rõ từ bảng giá. Dòng còn mơ hồ được giữ ở trạng thái
# Cần xác minh và không được chọn mặc định để tránh tạo sai sản phẩm.
RAW_ITEMS = [
    ("Hoa bi trắng", 145, True), ("Cỏ tứ giác", 60, True), ("Đèn rũ xanh", 110, False),
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


def product_description(name: str, confirmed: bool) -> str:
    """Sinh mô tả catalogue thận trọng, không tự suy đoán quy cách bán."""
    lower = name.casefold()
    if not confirmed:
        return (
            f"{name} dùng cắm hoa và trang trí. Tên thương mại và mẫu thực tế cần được xác nhận "
            "với nhà cung cấp trước khi đăng bán."
        )
    if "cẩm tú cầu" in lower:
        feature = "cụm hoa tròn gồm nhiều bông nhỏ"
    elif "delphinium" in lower or "phi yến" in lower:
        feature = "dáng cành cao với các bông hoa xếp dọc thân"
    elif "hồng chùm" in lower:
        feature = "nhiều bông nhỏ trên cùng một cành, tạo độ đầy tự nhiên"
    elif "hoa hồng" in lower:
        feature = "dáng hoa hồng nhiều lớp cánh, phù hợp làm hoa chủ đạo"
    elif "protea" in lower:
        feature = "bông có hình khối nổi bật, thích hợp tạo điểm nhấn"
    elif "tulip" in lower:
        feature = "dáng hoa thanh gọn, phù hợp phong cách cắm tối giản"
    elif "allium" in lower:
        feature = "cụm hoa dạng cầu trên cành thẳng, tạo điểm nhấn hình khối"
    elif "wax" in lower:
        feature = "nhiều bông nhỏ trên cành, phù hợp làm hoa phụ"
    elif "thược dược" in lower:
        feature = "bông nhiều lớp cánh, thích hợp làm điểm nhấn cho bình hoa"
    elif "cát tường" in lower:
        feature = "cánh hoa mềm, nhiều lớp, phù hợp bó hoa và cắm bình"
    elif "cúc nhí" in lower:
        feature = "bông nhỏ, thích hợp làm hoa phụ và tạo độ thoáng"
    elif "bi trắng" in lower:
        feature = "cụm hoa trắng nhỏ, thường dùng làm hoa phụ"
    elif "jasmine hoa" in lower:
        feature = "cành hoa nhỏ, phù hợp phối bó và trang trí nhẹ nhàng"
    elif "jasmine lá" in lower:
        feature = "cành lá xanh dùng tạo nền và đường nét cho thiết kế hoa"
    elif lower.startswith("lá ") or "cành thiên môn" in lower or "tùng" in lower:
        feature = "cành lá trang trí dùng tạo nền, độ xanh và đường nét"
    elif "dây rối" in lower:
        feature = "phụ liệu dạng dây dùng tạo đường nét cho thiết kế hoa"
    elif "cành san hô" in lower or "cỏ thép" in lower:
        feature = "cành trang trí có đường nét rõ, thích hợp tạo điểm nhấn"
    else:
        feature = "hoa hoặc cành trang trí dùng phối bó và cắm bình"
    return (
        f"{name}, {feature}. Sản phẩm bán theo mẫu hình; màu sắc, độ nở và hình dáng "
        "có thể chênh lệch nhẹ theo từng lô hoa."
    )[:300]


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
            "Mô tả": product_description(name, confirmed),
            "Tên file ảnh 1": "",
            "Tên file ảnh 2": "",
            "Tên file ảnh 3": "",
            "Tên file ảnh 4": "",
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


def safe_image_filename(product_name: str, slot: int, extension: str = "png") -> str:
    """Tạo tên ảnh ASCII ổn định để CSV và ZIP luôn khớp nhau."""
    plain = unicodedata.normalize("NFKD", product_name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", plain).strip("_").lower() or "san_pham"
    return f"{slug[:55]}_{slot}.{extension.lower()}"


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError("Không đọc được CSV trong mẫu Grab.")


def _zip_path_is_unsafe(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    return name.startswith(("/", "\\")) or ".." in parts


def _validate_image_name(name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.(?:jpg|png)", name, flags=re.IGNORECASE):
        raise ValueError(
            f"Tên ảnh '{name}' không hợp lệ. Chỉ dùng chữ không dấu, số, gạch dưới/gạch nối và đuôi .jpg hoặc .png."
        )


def build_create_items_zip(template_raw: bytes, products: pd.DataFrame, images: dict[str, bytes]) -> tuple[bytes, list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(template_raw)) as archive:
            unsafe = [n for n in archive.namelist() if _zip_path_is_unsafe(n)]
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

    department_member = next(
        (name for name in members if name.replace("\\", "/").lower() == "resources/department_list.csv"),
        None,
    )
    if department_member is None:
        raise ValueError("Mẫu thiếu resources/department_list.csv nên không thể kiểm tra danh mục Grab.")
    departments = pd.read_csv(
        io.StringIO(_decode(members[department_member])), dtype=str, keep_default_na=False
    )
    if "sub-department" not in departments.columns:
        raise ValueError("Danh sách danh mục trong mẫu không có cột sub-department.")
    valid_categories = set(departments["sub-department"].astype(str).str.strip())

    selected = products[products["Chọn tạo"].astype(bool)].copy()
    if selected.empty:
        raise ValueError("Chưa chọn sản phẩm nào để tạo.")
    if selected["Tên sản phẩm"].astype(str).str.strip().eq("").any() or selected["Giá bán (₫)"].isna().any():
        raise ValueError("Tên sản phẩm hoặc giá bán chưa hợp lệ.")
    if selected["Tình trạng tên"].eq("Cần xác minh với vựa").any():
        raise ValueError("Còn sản phẩm chưa xác minh tên. Hãy bỏ chọn hoặc xác nhận tên trước.")
    invalid_categories = sorted(
        set(selected["Danh mục Grab"].astype(str).str.strip()).difference(valid_categories)
    )
    if invalid_categories:
        raise ValueError(
            "Danh mục không khớp resources/department_list.csv: " + ", ".join(invalid_categories)
        )
    if len(selected) > 20_000:
        raise ValueError("GrabMerchant chỉ cho phép tối đa 20.000 món trong một lần cập nhật hàng loạt.")

    for image_name, image_content in images.items():
        _validate_image_name(image_name)
        if len(image_content) > 2 * 1024 * 1024:
            raise ValueError(f"Ảnh '{image_name}' vượt quá giới hạn 2 MB của Grab.")

    # Giữ dòng hướng dẫn đầu tiên của mẫu nếu có; xóa các dòng ví dụ phía sau.
    instruction = template.iloc[:1].copy()
    rows = []
    missing_images = []
    for _, product in selected.iterrows():
        row = {column: "" for column in template.columns}
        row["*ItemName"] = str(product["Tên sản phẩm"]).strip()
        row["*Price"] = str(int(product["Giá bán (₫)"]))
        row["*GrabCategoryName"] = str(product["Danh mục Grab"]).strip()
        # Để trống để Grab tự dùng lịch bán mặc định của cửa hàng theo hướng dẫn chính thức.
        if "AvailabilitySchedule" in row:
            row["AvailabilitySchedule"] = ""
        if "*AvailableStatus" in row:
            row["*AvailableStatus"] = "AVAILABLE"
        if "Description" in row:
            row["Description"] = str(product["Mô tả"])[:300]
        if "BarcodeNumber" in row:
            row["BarcodeNumber"] = ""
        if "SKUNumber" in row:
            row["SKUNumber"] = ""
        for slot in range(1, 5):
            photo_column = f"Photo{slot}"
            source_column = f"Tên file ảnh {slot}"
            image_name = str(product.get(source_column, "")).strip()
            if photo_column in row and image_name:
                _validate_image_name(image_name)
                if image_name not in images:
                    missing_images.append(image_name)
                else:
                    row[photo_column] = image_name
        rows.append(row)
    if missing_images:
        raise ValueError("Thiếu file ảnh đã khai báo: " + ", ".join(sorted(set(missing_images))))
    output_csv = pd.concat([instruction, pd.DataFrame(rows, columns=template.columns)], ignore_index=True)
    members[csv_name] = output_csv.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
    # Ảnh ví dụ đi kèm mẫu chỉ để minh họa, không phải ảnh sản phẩm sẽ tạo.
    members.pop("images/example_photo.jpg", None)
    for name, content in images.items():
        members[f"images/{name}"] = content
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    result = output.getvalue()
    if len(result) > 200 * 1024 * 1024:
        raise ValueError("Tệp ZIP đầu ra vượt quá giới hạn 200 MB của Grab.")
    return result, selected["Tên sản phẩm"].tolist()

from __future__ import annotations

import base64
from pathlib import Path

import streamlit.components.v1 as components


_FRONTEND = Path(__file__).resolve().parent.parent / "components" / "clipboard_image"
_paste_zone = components.declare_component("grabmart_clipboard_image", path=str(_FRONTEND))


def paste_image_zone(label: str, key: str) -> dict | None:
    """Nhận ảnh từ thao tác Ctrl+V do người dùng chủ động thực hiện."""
    return _paste_zone(label=label, key=key, default=None)


def decode_pasted_image(value: dict) -> tuple[bytes, str, str]:
    data_url = str(value.get("dataUrl", ""))
    mime = str(value.get("mime", ""))
    token = str(value.get("token", ""))
    if not data_url.startswith("data:image/") or "," not in data_url:
        raise ValueError("Clipboard không chứa ảnh hợp lệ.")
    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise ValueError("Định dạng ảnh dán không được hỗ trợ.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Không giải mã được ảnh từ clipboard.") from exc
    extension = "jpg" if mime in {"image/jpeg", "image/jpg"} else "png"
    return content, extension, token

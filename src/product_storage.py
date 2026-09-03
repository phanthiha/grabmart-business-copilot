"""Persistent product registry and images stored entirely in BigQuery."""
from __future__ import annotations
import re
import unicodedata
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

@dataclass(frozen=True)
class ProductStorageSettings:
    project_id: str
    dataset_id: str
    table_id: str
    image_table_id: str
    store_id: str
    @property
    def full_table_id(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"
    @property
    def full_image_table_id(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.image_table_id}"

def _safe_identifier(value: str, label: str, allow_hyphen: bool = False) -> str:
    pattern = r"[A-Za-z0-9_-]+" if allow_hyphen else r"[A-Za-z0-9_]+"
    if not value or not re.fullmatch(pattern, value):
        raise ValueError(f"{label} trong Secrets không hợp lệ.")
    return value

def get_product_storage_settings() -> ProductStorageSettings | None:
    if not bool(st.secrets.get("enable_product_storage", False)):
        return None
    required = {
        "project_id": st.secrets.get("project_id", ""),
        "dataset_id": st.secrets.get("dataset_id", ""),
        "table_id": st.secrets.get("product_registry_table", ""),
        "image_table_id": st.secrets.get("product_image_table", ""),
        "store_id": st.secrets.get("store_id", ""),
    }
    missing = [key for key, value in required.items() if not str(value).strip()]
    if missing:
        raise ValueError("Thiếu cấu hình lưu trữ: " + ", ".join(missing))
    return ProductStorageSettings(
        project_id=_safe_identifier(str(required["project_id"]), "project_id", True),
        dataset_id=_safe_identifier(str(required["dataset_id"]), "dataset_id"),
        table_id=_safe_identifier(str(required["table_id"]), "product_registry_table"),
        image_table_id=_safe_identifier(str(required["image_table_id"]), "product_image_table"),
        store_id=_safe_identifier(str(required["store_id"]), "store_id", True),
    )

def _client(settings: ProductStorageSettings) -> bigquery.Client:
    credentials = service_account.Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]))
    return bigquery.Client(project=settings.project_id, credentials=credentials)

def product_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")[:100] or "san-pham"

def ensure_product_registry(settings: ProductStorageSettings) -> None:
    client = _client(settings)
    # Tables are provisioned once by the project owner. Runtime credentials only
    # need read/write access to these exact tables, not dataset create privileges.
    client.get_table(settings.full_table_id)
    client.get_table(settings.full_image_table_id)

def load_product_registry(settings: ProductStorageSettings) -> pd.DataFrame:
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("store_id", "STRING", settings.store_id)])
    return _client(settings).query(
        f"""SELECT * FROM `{settings.full_table_id}` WHERE store_id=@store_id
        QUALIFY ROW_NUMBER() OVER(PARTITION BY store_id,product_key ORDER BY updated_at DESC)=1
        ORDER BY product_name""",
        job_config=config,
    ).to_dataframe()

def _existing_image_slots(settings: ProductStorageSettings) -> dict[str, set[int]]:
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("store_id", "STRING", settings.store_id)])
    rows = _client(settings).query(
        f"SELECT product_key,image_slot FROM `{settings.full_image_table_id}` WHERE store_id=@store_id",
        job_config=config,
    ).result()
    slots: dict[str, set[int]] = {}
    for row in rows:
        slots.setdefault(str(row.product_key), set()).add(int(row.image_slot))
    return slots

def _image_row(settings: ProductStorageSettings, name: str, slot: int,
               stored: dict[str, Any], updated_by: str, updated_at: str) -> dict[str, Any]:
    content = bytes(stored["content"])
    if len(content) > 2 * 1024 * 1024:
        raise ValueError(f"Ảnh {slot} của {name} vượt giới hạn 2 MB.")
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", str(stored["filename"]))
    content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    return {
        "store_id": settings.store_id, "product_key": product_key(name),
        "product_name": name, "image_slot": slot, "filename": filename,
        "content_type": content_type, "image_bytes": base64.b64encode(content).decode("ascii"),
        "byte_size": len(content), "updated_by": updated_by, "updated_at": updated_at,
    }

def save_products(settings: ProductStorageSettings, products: pd.DataFrame,
                  image_store: dict[tuple[str, int], dict[str, Any]],
                  uploaded_products: set[str], ready_products: set[str], updated_by: str) -> int:
    ensure_product_registry(settings)
    client = _client(settings)
    existing_slots = _existing_image_slots(settings)
    saved_at = datetime.now(timezone.utc).isoformat()
    product_rows: list[dict[str, Any]] = []
    image_rows: list[dict[str, Any]] = []
    for _, row in products.drop_duplicates(subset=["Tên sản phẩm"], keep="last").iterrows():
        name = str(row["Tên sản phẩm"]).strip()
        key = product_key(name)
        slots = set(existing_slots.get(key, set()))
        for slot in range(1, 5):
            stored = image_store.get((name, slot))
            if stored:
                image_rows.append(_image_row(settings, name, slot, stored, updated_by, saved_at))
                slots.add(slot)
        uploaded = name in uploaded_products
        status = "UPLOADED_TO_GRAB" if uploaded else ("READY" if name in ready_products else "DRAFT")
        product_rows.append({
            "store_id": settings.store_id, "product_key": key, "product_name": name,
            "supplier_cost_vnd": int(row["Giá gốc (₫)"]),
            "selling_price_vnd": int(row["Giá bán (₫)"]),
            "price_multiplier": float(row["Hệ số giá"]), "description": str(row["Mô tả"]),
            "name_status": str(row["Tình trạng tên"]), "workflow_status": status,
            "uploaded_to_grab": uploaded, "grab_uploaded_at": saved_at if uploaded else None,
            "image_count": len(slots), "updated_by": updated_by, "updated_at": saved_at,
        })
    load_config = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_APPEND)
    if image_rows:
        client.load_table_from_json(image_rows, settings.full_image_table_id, job_config=load_config).result()
    if product_rows:
        client.load_table_from_json(product_rows, settings.full_table_id, job_config=load_config).result()
    return len(product_rows)

def download_registry_images(settings: ProductStorageSettings, registry: pd.DataFrame) -> dict[tuple[str, int], dict[str, Any]]:
    del registry
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("store_id", "STRING", settings.store_id)])
    rows = _client(settings).query(
        f"""SELECT product_name,image_slot,filename,image_bytes
        FROM `{settings.full_image_table_id}` WHERE store_id=@store_id
        QUALIFY ROW_NUMBER() OVER(PARTITION BY store_id,product_key,image_slot ORDER BY updated_at DESC)=1
        ORDER BY product_name,image_slot""",
        job_config=config,
    ).result()
    return {(str(row.product_name), int(row.image_slot)): {"filename": str(row.filename), "content": bytes(row.image_bytes)} for row in rows}

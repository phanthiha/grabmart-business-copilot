"""Persistent product registry and images stored entirely in BigQuery."""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
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
        f"SELECT * FROM `{settings.full_table_id}` WHERE store_id=@store_id ORDER BY product_name",
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

def _save_image(settings: ProductStorageSettings, client: bigquery.Client, name: str, slot: int, stored: dict[str, Any], updated_by: str) -> None:
    content = bytes(stored["content"])
    if len(content) > 2 * 1024 * 1024:
        raise ValueError(f"Ảnh {slot} của {name} vượt giới hạn 2 MB.")
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", str(stored["filename"]))
    content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    params = [
        bigquery.ScalarQueryParameter("store_id", "STRING", settings.store_id),
        bigquery.ScalarQueryParameter("product_key", "STRING", product_key(name)),
        bigquery.ScalarQueryParameter("product_name", "STRING", name),
        bigquery.ScalarQueryParameter("image_slot", "INT64", slot),
        bigquery.ScalarQueryParameter("filename", "STRING", filename),
        bigquery.ScalarQueryParameter("content_type", "STRING", content_type),
        bigquery.ScalarQueryParameter("image_bytes", "BYTES", content),
        bigquery.ScalarQueryParameter("byte_size", "INT64", len(content)),
        bigquery.ScalarQueryParameter("updated_by", "STRING", updated_by),
    ]
    client.query(f"""MERGE `{settings.full_image_table_id}` T
      USING (SELECT @store_id store_id,@product_key product_key,@image_slot image_slot) S
      ON T.store_id=S.store_id AND T.product_key=S.product_key AND T.image_slot=S.image_slot
      WHEN MATCHED THEN UPDATE SET product_name=@product_name,filename=@filename,
        content_type=@content_type,image_bytes=@image_bytes,byte_size=@byte_size,
        updated_by=@updated_by,updated_at=CURRENT_TIMESTAMP()
      WHEN NOT MATCHED THEN INSERT (store_id,product_key,product_name,image_slot,filename,
        content_type,image_bytes,byte_size,updated_by,updated_at)
      VALUES (@store_id,@product_key,@product_name,@image_slot,@filename,@content_type,
        @image_bytes,@byte_size,@updated_by,CURRENT_TIMESTAMP())""",
      job_config=bigquery.QueryJobConfig(query_parameters=params)).result()

def save_products(settings: ProductStorageSettings, products: pd.DataFrame,
                  image_store: dict[tuple[str, int], dict[str, Any]],
                  uploaded_products: set[str], ready_products: set[str], updated_by: str) -> int:
    ensure_product_registry(settings)
    client = _client(settings)
    existing_slots = _existing_image_slots(settings)
    merge_sql = f"""MERGE `{settings.full_table_id}` T
      USING (SELECT @store_id store_id,@product_key product_key) S
      ON T.store_id=S.store_id AND T.product_key=S.product_key
      WHEN MATCHED THEN UPDATE SET product_name=@product_name,supplier_cost_vnd=@supplier_cost_vnd,
        selling_price_vnd=@selling_price_vnd,price_multiplier=@price_multiplier,
        description=@description,name_status=@name_status,workflow_status=@workflow_status,
        uploaded_to_grab=@uploaded_to_grab,
        grab_uploaded_at=IF(@uploaded_to_grab,COALESCE(T.grab_uploaded_at,CURRENT_TIMESTAMP()),NULL),
        image_count=@image_count,updated_by=@updated_by,updated_at=CURRENT_TIMESTAMP()
      WHEN NOT MATCHED THEN INSERT (store_id,product_key,product_name,supplier_cost_vnd,
        selling_price_vnd,price_multiplier,description,name_status,workflow_status,
        uploaded_to_grab,grab_uploaded_at,image_count,updated_by,updated_at)
      VALUES (@store_id,@product_key,@product_name,@supplier_cost_vnd,@selling_price_vnd,
        @price_multiplier,@description,@name_status,@workflow_status,@uploaded_to_grab,
        IF(@uploaded_to_grab,CURRENT_TIMESTAMP(),NULL),@image_count,@updated_by,CURRENT_TIMESTAMP())"""
    saved = 0
    for _, row in products.drop_duplicates(subset=["Tên sản phẩm"], keep="last").iterrows():
        name = str(row["Tên sản phẩm"]).strip()
        key = product_key(name)
        slots = set(existing_slots.get(key, set()))
        for slot in range(1, 5):
            stored = image_store.get((name, slot))
            if stored:
                _save_image(settings, client, name, slot, stored, updated_by)
                slots.add(slot)
        uploaded = name in uploaded_products
        status = "UPLOADED_TO_GRAB" if uploaded else ("READY" if name in ready_products else "DRAFT")
        params = [
            bigquery.ScalarQueryParameter("store_id", "STRING", settings.store_id),
            bigquery.ScalarQueryParameter("product_key", "STRING", key),
            bigquery.ScalarQueryParameter("product_name", "STRING", name),
            bigquery.ScalarQueryParameter("supplier_cost_vnd", "INT64", int(row["Giá gốc (₫)"])),
            bigquery.ScalarQueryParameter("selling_price_vnd", "INT64", int(row["Giá bán (₫)"])),
            bigquery.ScalarQueryParameter("price_multiplier", "FLOAT64", float(row["Hệ số giá"])),
            bigquery.ScalarQueryParameter("description", "STRING", str(row["Mô tả"])),
            bigquery.ScalarQueryParameter("name_status", "STRING", str(row["Tình trạng tên"])),
            bigquery.ScalarQueryParameter("workflow_status", "STRING", status),
            bigquery.ScalarQueryParameter("uploaded_to_grab", "BOOL", uploaded),
            bigquery.ScalarQueryParameter("image_count", "INT64", len(slots)),
            bigquery.ScalarQueryParameter("updated_by", "STRING", updated_by),
        ]
        client.query(merge_sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        saved += 1
    return saved

def download_registry_images(settings: ProductStorageSettings, registry: pd.DataFrame) -> dict[tuple[str, int], dict[str, Any]]:
    del registry
    config = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("store_id", "STRING", settings.store_id)])
    rows = _client(settings).query(
        f"SELECT product_name,image_slot,filename,image_bytes FROM `{settings.full_image_table_id}` WHERE store_id=@store_id ORDER BY product_name,image_slot",
        job_config=config,
    ).result()
    return {(str(row.product_name), int(row.image_slot)): {"filename": str(row.filename), "content": bytes(row.image_bytes)} for row in rows}

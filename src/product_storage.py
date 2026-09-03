"""Persistent product registry backed by BigQuery and private Cloud Storage."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st
from google.cloud import bigquery, storage
from google.oauth2 import service_account


@dataclass(frozen=True)
class ProductStorageSettings:
    project_id: str
    dataset_id: str
    table_id: str
    bucket_name: str
    store_id: str

    @property
    def full_table_id(self) -> str:
        return f"{self.project_id}.{self.dataset_id}.{self.table_id}"


def _safe_identifier(
    value: str, label: str, allow_hyphen: bool = False, allow_dot: bool = False
) -> str:
    pattern = r"[A-Za-z0-9_.-]+" if allow_dot else (r"[A-Za-z0-9_-]+" if allow_hyphen else r"[A-Za-z0-9_]+")
    if not value or not re.fullmatch(pattern, value):
        raise ValueError(f"{label} trong Secrets không hợp lệ.")
    return value


def get_product_storage_settings() -> ProductStorageSettings | None:
    """Return validated settings, or None while persistent storage is disabled."""
    if not bool(st.secrets.get("enable_product_storage", False)):
        return None
    required = {
        "project_id": st.secrets.get("project_id", ""),
        "dataset_id": st.secrets.get("dataset_id", ""),
        "table_id": st.secrets.get("product_registry_table", ""),
        "bucket_name": st.secrets.get("product_image_bucket", ""),
        "store_id": st.secrets.get("store_id", ""),
    }
    missing = [key for key, value in required.items() if not str(value).strip()]
    if missing:
        raise ValueError("Thiếu cấu hình lưu trữ: " + ", ".join(missing))
    return ProductStorageSettings(
        project_id=_safe_identifier(str(required["project_id"]), "project_id", True),
        dataset_id=_safe_identifier(str(required["dataset_id"]), "dataset_id"),
        table_id=_safe_identifier(str(required["table_id"]), "product_registry_table"),
        bucket_name=_safe_identifier(str(required["bucket_name"]), "product_image_bucket", True, True),
        store_id=_safe_identifier(str(required["store_id"]), "store_id", True),
    )


def _credentials():
    account = dict(st.secrets["gcp_service_account"])
    return service_account.Credentials.from_service_account_info(account)


def _clients(settings: ProductStorageSettings):
    credentials = _credentials()
    return (
        bigquery.Client(project=settings.project_id, credentials=credentials),
        storage.Client(project=settings.project_id, credentials=credentials),
    )


def product_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return key[:100] or "san-pham"


def ensure_product_registry(settings: ProductStorageSettings) -> None:
    bq, _ = _clients(settings)
    sql = f"""
    CREATE TABLE IF NOT EXISTS `{settings.full_table_id}` (
      store_id STRING,
      product_key STRING,
      product_name STRING,
      supplier_cost_vnd INT64,
      selling_price_vnd INT64,
      price_multiplier FLOAT64,
      description STRING,
      name_status STRING,
      workflow_status STRING,
      uploaded_to_grab BOOL,
      grab_uploaded_at TIMESTAMP,
      photo1_uri STRING,
      photo2_uri STRING,
      photo3_uri STRING,
      photo4_uri STRING,
      image_count INT64,
      updated_by STRING,
      updated_at TIMESTAMP
    )
    CLUSTER BY store_id, product_key
    """
    bq.query(sql).result()


def load_product_registry(settings: ProductStorageSettings) -> pd.DataFrame:
    bq, _ = _clients(settings)
    sql = f"""
    SELECT * FROM `{settings.full_table_id}`
    WHERE store_id = @store_id
    ORDER BY product_name
    """
    config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("store_id", "STRING", settings.store_id)]
    )
    return bq.query(sql, job_config=config).to_dataframe()


def _upload_images(
    settings: ProductStorageSettings,
    storage_client: storage.Client,
    name: str,
    image_store: dict[tuple[str, int], dict[str, Any]],
    existing_uris: list[str],
) -> list[str]:
    bucket = storage_client.bucket(settings.bucket_name)
    uris: list[str] = []
    for slot in range(1, 5):
        stored = image_store.get((name, slot))
        if not stored:
            # A browser rerun may not have downloaded the bytes yet. Preserve the
            # private object reference instead of accidentally clearing it.
            uris.append(existing_uris[slot - 1])
            continue
        filename = re.sub(r"[^A-Za-z0-9._-]", "_", str(stored["filename"]))
        object_name = f"stores/{settings.store_id}/products/{product_key(name)}/{slot}_{filename}"
        extension = filename.rsplit(".", 1)[-1].lower()
        content_type = "image/png" if extension == "png" else "image/jpeg"
        blob = bucket.blob(object_name)
        blob.upload_from_string(stored["content"], content_type=content_type)
        uris.append(f"gs://{settings.bucket_name}/{object_name}")
    return uris


def save_products(
    settings: ProductStorageSettings,
    products: pd.DataFrame,
    image_store: dict[tuple[str, int], dict[str, Any]],
    uploaded_products: set[str],
    ready_products: set[str],
    updated_by: str,
) -> int:
    """Upsert product metadata and private image object paths."""
    ensure_product_registry(settings)
    bq, storage_client = _clients(settings)
    try:
        existing_registry = load_product_registry(settings)
    except Exception:
        existing_registry = pd.DataFrame()
    existing_by_key = {
        str(row["product_key"]): row for _, row in existing_registry.iterrows()
    }
    merge_sql = f"""
    MERGE `{settings.full_table_id}` T
    USING (SELECT @store_id store_id, @product_key product_key) S
    ON T.store_id = S.store_id AND T.product_key = S.product_key
    WHEN MATCHED THEN UPDATE SET
      product_name=@product_name, supplier_cost_vnd=@supplier_cost_vnd,
      selling_price_vnd=@selling_price_vnd, price_multiplier=@price_multiplier,
      description=@description, name_status=@name_status,
      workflow_status=@workflow_status, uploaded_to_grab=@uploaded_to_grab,
      grab_uploaded_at=IF(@uploaded_to_grab, COALESCE(T.grab_uploaded_at, CURRENT_TIMESTAMP()), NULL),
      photo1_uri=@photo1_uri, photo2_uri=@photo2_uri,
      photo3_uri=@photo3_uri, photo4_uri=@photo4_uri,
      image_count=@image_count, updated_by=@updated_by, updated_at=CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT
      (store_id, product_key, product_name, supplier_cost_vnd, selling_price_vnd,
       price_multiplier, description, name_status, workflow_status, uploaded_to_grab,
       grab_uploaded_at, photo1_uri, photo2_uri, photo3_uri, photo4_uri,
       image_count, updated_by, updated_at)
    VALUES
      (@store_id, @product_key, @product_name, @supplier_cost_vnd, @selling_price_vnd,
       @price_multiplier, @description, @name_status, @workflow_status, @uploaded_to_grab,
       IF(@uploaded_to_grab, CURRENT_TIMESTAMP(), NULL), @photo1_uri, @photo2_uri,
       @photo3_uri, @photo4_uri, @image_count, @updated_by, CURRENT_TIMESTAMP())
    """
    saved = 0
    for _, row in products.drop_duplicates(subset=["Tên sản phẩm"], keep="last").iterrows():
        name = str(row["Tên sản phẩm"]).strip()
        key = product_key(name)
        existing = existing_by_key.get(key)
        existing_uris = []
        for slot in range(1, 5):
            value = existing.get(f"photo{slot}_uri", "") if existing is not None else ""
            existing_uris.append("" if pd.isna(value) else str(value or ""))
        uris = _upload_images(settings, storage_client, name, image_store, existing_uris)
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
            *[bigquery.ScalarQueryParameter(f"photo{i + 1}_uri", "STRING", uri) for i, uri in enumerate(uris)],
            bigquery.ScalarQueryParameter("image_count", "INT64", sum(bool(uri) for uri in uris)),
            bigquery.ScalarQueryParameter("updated_by", "STRING", updated_by),
        ]
        bq.query(merge_sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        saved += 1
    return saved


def download_registry_images(
    settings: ProductStorageSettings,
    registry: pd.DataFrame,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Download only objects in the configured private bucket."""
    _, storage_client = _clients(settings)
    restored: dict[tuple[str, int], dict[str, Any]] = {}
    prefix = f"gs://{settings.bucket_name}/"
    for _, row in registry.iterrows():
        name = str(row["product_name"])
        for slot in range(1, 5):
            uri = str(row.get(f"photo{slot}_uri", "") or "")
            if not uri.startswith(prefix):
                continue
            object_name = uri[len(prefix):]
            content = storage_client.bucket(settings.bucket_name).blob(object_name).download_as_bytes()
            filename = object_name.rsplit("/", 1)[-1]
            if filename.startswith(f"{slot}_"):
                filename = filename[len(f"{slot}_"):]
            restored[(name, slot)] = {"filename": filename, "content": content}
    return restored

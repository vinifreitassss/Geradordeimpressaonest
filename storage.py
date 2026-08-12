from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
UPLOADS_DIR = DATA_DIR / "uploads"
ORDERS_DIR = DATA_DIR / "orders"
OUTPUT_DIR = DATA_DIR / "output"
MODELS_INDEX = DATA_DIR / "models.json"


def ensure_dirs() -> None:
    for path in (DATA_DIR, MODELS_DIR, UPLOADS_DIR, ORDERS_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not MODELS_INDEX.exists():
        MODELS_INDEX.write_text("[]", encoding="utf-8")


def load_models() -> list[dict[str, Any]]:
    ensure_dirs()
    return json.loads(MODELS_INDEX.read_text(encoding="utf-8"))


def save_models(models: list[dict[str, Any]]) -> None:
    ensure_dirs()
    MODELS_INDEX.write_text(json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8")


def add_model(name: str, width_mm: float, height_mm: float, pdf_source: Path) -> dict[str, Any]:
    models = load_models()
    model_id = uuid.uuid4().hex[:10]
    dest = MODELS_DIR / f"{model_id}.pdf"
    shutil.copy2(pdf_source, dest)
    model = {
        "id": model_id,
        "name": name,
        "width_mm": float(width_mm),
        "height_mm": float(height_mm),
        "pdf_path": str(dest.relative_to(BASE_DIR)),
        "spacing_mm": 2.0,
        "rotation_allowed": True,
    }
    models.append(model)
    save_models(models)
    return model


def get_model(model_id: str) -> dict[str, Any]:
    for model in load_models():
        if model["id"] == model_id:
            return model
    raise KeyError(f"Modelo não encontrado: {model_id}")


def save_order(order: dict[str, Any]) -> dict[str, Any]:
    ensure_dirs()
    path = ORDERS_DIR / f"{order['id']}.json"
    path.write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")
    return order


def load_orders(status: str | None = None) -> list[dict[str, Any]]:
    ensure_dirs()
    orders: list[dict[str, Any]] = []
    for path in ORDERS_DIR.glob("*.json"):
        try:
            order = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if status is None or order.get("status") == status:
            orders.append(order)
    orders.sort(key=lambda item: item.get("created_at", ""))
    return orders


def update_order(order_id: str, **changes: Any) -> dict[str, Any]:
    path = ORDERS_DIR / f"{order_id}.json"
    order = json.loads(path.read_text(encoding="utf-8"))
    order.update(changes)
    save_order(order)
    return order


def store_upload(source: Path, suffix: str) -> str:
    ensure_dirs()
    filename = f"{uuid.uuid4().hex}{suffix.lower()}"
    dest = UPLOADS_DIR / filename
    shutil.copy2(source, dest)
    return str(dest.relative_to(BASE_DIR))

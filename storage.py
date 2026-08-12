from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import fitz

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = DATA_DIR / "models"
UPLOADS_DIR = DATA_DIR / "uploads"
ORDERS_DIR = DATA_DIR / "orders"
OUTPUT_DIR = DATA_DIR / "output"
MODELS_INDEX = DATA_DIR / "models.json"
PRESETS_DIR = BASE_DIR / "presets"

MM_PER_POINT = 25.4 / 72.0

BUILTIN_PRESETS = [
    ("med5", "Medalha 5 cm", "linhacorte-med5cm.pdf"),
    ("med6", "Medalha 6 cm", "linhacorte-med6cm.pdf"),
    ("med7", "Medalha 7 cm", "linhacorte-med7cm.pdf"),
    ("med8", "Medalha 8 cm", "linhacorte-med8cm.pdf"),
    ("trf210_45", "TRF210 45 cm", "linhacorte-TRF210-45cm.pdf"),
]


def inspect_cut_pdf(pdf_source: Path) -> dict[str, Any]:
    """Valida o template e usa o tamanho físico do próprio PDF como autoridade."""
    raw = pdf_source.read_bytes()
    if b"CutContour" not in raw or b"Separation" not in raw:
        raise ValueError(
            "O PDF não contém a spot color CutContour como separação. "
            "Exporte o arquivo de corte mantendo a cor especial CutContour."
        )

    doc = fitz.open(pdf_source)
    try:
        if doc.page_count != 1:
            raise ValueError("O PDF base do corte deve ter exatamente uma página.")
        page = doc[0]
        width_mm = page.rect.width * MM_PER_POINT
        height_mm = page.rect.height * MM_PER_POINT
        if width_mm <= 0 or height_mm <= 0:
            raise ValueError("O PDF base possui dimensões inválidas.")
        return {
            "width_mm": round(width_mm, 4),
            "height_mm": round(height_mm, 4),
            "has_cut_contour": True,
        }
    finally:
        doc.close()


def _read_models_index() -> list[dict[str, Any]]:
    try:
        return json.loads(MODELS_INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []


def _ensure_builtin_models() -> None:
    models = _read_models_index()
    by_id = {m.get("id"): m for m in models}
    changed = False

    for model_id, name, filename in BUILTIN_PRESETS:
        path = PRESETS_DIR / filename
        if not path.exists():
            continue
        info = inspect_cut_pdf(path)
        model = {
            "id": model_id,
            "name": name,
            "width_mm": info["width_mm"],
            "height_mm": info["height_mm"],
            "pdf_path": str(path.relative_to(BASE_DIR)),
            "spacing_mm": 2.0,
            "rotation_allowed": True,
            "cut_contour": "CutContour",
            "dimensions_source": "pdf_page",
            "builtin": True,
        }
        if by_id.get(model_id) != model:
            by_id[model_id] = model
            changed = True

    if changed:
        ordered = []
        builtin_ids = {x[0] for x in BUILTIN_PRESETS}
        for model_id, _, _ in BUILTIN_PRESETS:
            if model_id in by_id:
                ordered.append(by_id[model_id])
        ordered.extend(m for m in models if m.get("id") not in builtin_ids)
        MODELS_INDEX.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_dirs() -> None:
    for path in (DATA_DIR, MODELS_DIR, UPLOADS_DIR, ORDERS_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not MODELS_INDEX.exists():
        MODELS_INDEX.write_text("[]", encoding="utf-8")
    _ensure_builtin_models()


def load_models() -> list[dict[str, Any]]:
    ensure_dirs()
    return _read_models_index()


def save_models(models: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_INDEX.write_text(json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8")


def add_model(name: str, width_mm: float, height_mm: float, pdf_source: Path) -> dict[str, Any]:
    """Cadastra um modelo adicional; dimensões são sempre lidas do PDF."""
    info = inspect_cut_pdf(pdf_source)
    models = load_models()
    model_id = uuid.uuid4().hex[:10]
    dest = MODELS_DIR / f"{model_id}.pdf"
    shutil.copy2(pdf_source, dest)
    model = {
        "id": model_id,
        "name": name,
        "width_mm": info["width_mm"],
        "height_mm": info["height_mm"],
        "pdf_path": str(dest.relative_to(BASE_DIR)),
        "spacing_mm": 2.0,
        "rotation_allowed": True,
        "cut_contour": "CutContour",
        "dimensions_source": "pdf_page",
        "builtin": False,
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

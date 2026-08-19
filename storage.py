from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

BASE_DIR = Path(__file__).resolve().parent
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


def builtin_models() -> list[dict[str, Any]]:
    models = []
    for model_id, name, filename in BUILTIN_PRESETS:
        path = PRESETS_DIR / filename
        if not path.exists():
            continue
        info = inspect_cut_pdf(path)
        models.append({
            "id": model_id,
            "name": name,
            "width_mm": info["width_mm"],
            "height_mm": info["height_mm"],
            "filename": filename,
            "builtin": True,
        })
    return models

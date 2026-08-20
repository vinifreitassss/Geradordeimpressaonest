from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI

from storage import BUILTIN_PRESETS, inspect_cut_pdf

app = FastAPI(title="Gerador de Impressão Nest")
BASE_DIR = Path(__file__).resolve().parents[1]
PRESETS_DIR = BASE_DIR / "presets"


@app.get("/api")
def api_home():
    return {
        "name": "Gerador de Impressão Nest",
        "stateless": True,
        "processing": "browser",
    }


@app.get("/api/presets")
def api_presets():
    result = []
    for model_id, name, filename in BUILTIN_PRESETS:
        path = PRESETS_DIR / filename
        if not path.exists():
            continue
        try:
            info = inspect_cut_pdf(path)
        except ValueError:
            continue
        result.append({
            "id": model_id,
            "name": name,
            "filename": filename,
            "width_mm": info["width_mm"],
            "height_mm": info["height_mm"],
        })
    return result

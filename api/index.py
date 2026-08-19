from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from nest import pack_order_blocks, split_order_blocks
from pdf_engine import build_order_pdf, compose_batch_pdf
from storage import BUILTIN_PRESETS, inspect_cut_pdf

app = FastAPI(title="Gerador de Impressão Nest")
BASE_DIR = Path(__file__).resolve().parents[1]
PRESETS_DIR = BASE_DIR / "presets"


@app.get("/api")
def api_home():
    return {"name": "Gerador de Impressão Nest", "stateless": True}


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
            "width_mm": info["width_mm"],
            "height_mm": info["height_mm"],
        })
    return result


@app.post("/api/inspect-model")
async def inspect_model(file: UploadFile = File(...)):
    if Path(file.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(400, "O arquivo de corte precisa ser PDF.")
    with tempfile.TemporaryDirectory(prefix="nest-inspect-") as td:
        path = Path(td) / "model.pdf"
        path.write_bytes(await file.read())
        try:
            return inspect_cut_pdf(path)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


async def _save_upload(upload: UploadFile, destination: Path, allowed: set[str]) -> None:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Formato não permitido: {upload.filename or 'arquivo'}")
    destination.write_bytes(await upload.read())


@app.post("/api/generate")
async def generate(
    orders: str = Form(...),
    models: str = Form(...),
    model_files: list[UploadFile] | None = File(default=None),
    artworks: list[UploadFile] | None = File(default=None),
):
    try:
        order_data = json.loads(orders)
        model_data = json.loads(models)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Dados da sessão inválidos.") from exc

    if not isinstance(order_data, list) or not order_data:
        raise HTTPException(400, "Adicione pelo menos um pedido.")
    if not isinstance(model_data, list) or not model_data:
        raise HTTPException(400, "Adicione pelo menos um modelo de corte.")

    model_files = model_files or []
    artworks = artworks or []

    with tempfile.TemporaryDirectory(prefix="gerador-nest-") as td:
        work = Path(td)
        model_dir = work / "models"
        upload_dir = work / "uploads"
        output_dir = work / "output"
        model_dir.mkdir()
        upload_dir.mkdir()
        output_dir.mkdir()

        models_by_key: dict[str, dict] = {}
        custom_files_by_key: dict[str, UploadFile] = {}

        for upload in model_files:
            key = Path(upload.filename or "").stem
            custom_files_by_key[key] = upload

        # Custom model files are identified by the browser-generated key in the filename.
        # The original filename is retained only for extension validation.
        for model in model_data:
            key = str(model.get("key", ""))
            name = str(model.get("name", "")).strip()
            builtin_id = model.get("builtin_id")
            if not key or not name:
                raise HTTPException(400, "Modelo de corte inválido.")

            if builtin_id:
                match = next((x for x in BUILTIN_PRESETS if x[0] == builtin_id), None)
                if not match:
                    raise HTTPException(400, f"Preset desconhecido: {builtin_id}")
                source = PRESETS_DIR / match[2]
                if not source.exists():
                    raise HTTPException(500, f"Preset ausente no servidor: {match[2]}")
                dest = model_dir / f"{key}.pdf"
                shutil.copy2(source, dest)
            else:
                upload = custom_files_by_key.get(key)
                if upload is None:
                    raise HTTPException(400, f"PDF do modelo '{name}' não foi enviado.")
                dest = model_dir / f"{key}.pdf"
                await _save_upload(upload, dest, {".pdf"})

            try:
                info = inspect_cut_pdf(dest)
            except ValueError as exc:
                raise HTTPException(400, f"Modelo '{name}': {exc}") from exc

            models_by_key[key] = {
                "id": key,
                "name": name,
                "width_mm": info["width_mm"],
                "height_mm": info["height_mm"],
                "pdf_path": str(dest.relative_to(work)),
            }

        if len(artworks) != len(order_data):
            raise HTTPException(400, "A quantidade de artes não corresponde à quantidade de pedidos.")

        normalized_orders = []
        for index, raw in enumerate(order_data):
            try:
                code = str(raw["code"]).strip()
                model_key = str(raw["model_key"])
                quantity = int(raw["quantity"])
                details = str(raw.get("details", "")).strip()
                art_scale = max(0.1, min(float(raw.get("art_scale", 1.0)), 5.0))
                offset_x_mm = float(raw.get("offset_x_mm", 0.0))
                offset_y_mm = float(raw.get("offset_y_mm", 0.0))
                art_rotation = int(raw.get("art_rotation", 0)) % 360
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(400, f"Pedido {index + 1} possui dados inválidos.") from exc

            if not code:
                raise HTTPException(400, f"Pedido {index + 1}: informe o código.")
            if quantity <= 0:
                raise HTTPException(400, f"Pedido {code}: quantidade deve ser maior que zero.")
            if model_key not in models_by_key:
                raise HTTPException(400, f"Pedido {code}: modelo de corte não encontrado.")

            artwork = artworks[index]
            suffix = Path(artwork.filename or "").suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise HTTPException(400, f"Pedido {code}: a arte deve ser PNG, JPG, JPEG ou WEBP.")
            image_path = upload_dir / f"{index:04d}{suffix}"
            await _save_upload(artwork, image_path, {".png", ".jpg", ".jpeg", ".webp"})

            normalized_orders.append({
                "id": uuid.uuid4().hex[:12],
                "code": code,
                "model_id": model_key,
                "quantity": quantity,
                "details": details,
                "image_path": str(image_path.relative_to(work)),
                "art_scale": art_scale,
                "offset_x_mm": offset_x_mm,
                "offset_y_mm": offset_y_mm,
                "art_rotation": art_rotation,
            })

        blocks = []
        valid_orders = []
        errors = []
        for order in normalized_orders:
            model = models_by_key[order["model_id"]]
            try:
                order_blocks = split_order_blocks(order, model)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            blocks.extend(order_blocks)
            valid_orders.append(order)

        if not blocks:
            raise HTTPException(400, "; ".join(errors) or "Nenhum pedido pôde ser montado.")

        try:
            sheets = pack_order_blocks(blocks)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        block_pdf_paths: dict[str, Path] = {}
        order_by_id = {o["id"]: o for o in valid_orders}
        model_by_order = {o["id"]: models_by_key[o["model_id"]] for o in valid_orders}

        for block in blocks:
            order = order_by_id[block.order_id]
            model = model_by_order[block.order_id]
            block_pdf_paths[block.block_id] = build_order_pdf(
                order, model, block, work, output_dir
            )

        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"impressao_{batch_id}.pdf"
        final_pdf = compose_batch_pdf(sheets, block_pdf_paths, filename, output_dir)
        pdf_bytes = final_pdf.read_bytes()

        sheet_info = []
        for sheet in sheets:
            codes = []
            for item in sheet["items"]:
                code = order_by_id[item["order_id"]]["code"]
                if code not in codes:
                    codes.append(code)
            sheet_info.append({
                "page": sheet["index"],
                "width_mm": sheet["width_mm"],
                "height_mm": round(sheet["height_mm"], 2),
                "utilization": round(sheet["utilization"] * 100, 1),
                "orders": codes,
            })

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Pages": str(len(sheets)),
            "X-Warnings": json.dumps(errors, ensure_ascii=False),
        }
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

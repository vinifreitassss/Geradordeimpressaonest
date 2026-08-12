from __future__ import annotations

import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from nest import SHEET_MAX_HEIGHT_MM, SHEET_WIDTH_MM, choose_order_block, pack_order_blocks
from pdf_engine import build_order_pdf, compose_sheet_pdf, render_pdf_preview
from storage import (
    BASE_DIR,
    OUTPUT_DIR,
    add_model,
    ensure_dirs,
    get_model,
    load_models,
    load_orders,
    save_order,
    store_upload,
    update_order,
)

app = FastAPI(title="Gerador de Impressão Nest")
ensure_dirs()


def temp_upload(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "arquivo").suffix
    fd, name = tempfile.mkstemp(suffix=suffix)
    path = Path(name)
    with open(fd, "wb", closefd=True) as target:
        shutil.copyfileobj(upload.file, target)
    return path


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return INDEX_HTML


@app.get("/api/models")
def api_models():
    return load_models()


@app.post("/api/models")
def api_create_model(
    name: str = Form(...),
    width_mm: float = Form(...),
    height_mm: float = Form(...),
    cut_pdf: UploadFile = File(...),
):
    if width_mm <= 0 or height_mm <= 0:
        raise HTTPException(400, "Dimensões inválidas")
    if Path(cut_pdf.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(400, "O arquivo de corte precisa ser PDF")
    tmp = temp_upload(cut_pdf)
    try:
        model = add_model(name.strip(), width_mm, height_mm, tmp)
    finally:
        tmp.unlink(missing_ok=True)
    return model


@app.get("/api/models/{model_id}/preview")
def model_preview(model_id: str):
    try:
        model = get_model(model_id)
    except KeyError:
        raise HTTPException(404, "Modelo não encontrado")
    png = render_pdf_preview(BASE_DIR / model["pdf_path"])
    return Response(content=png, media_type="image/png")


@app.get("/api/orders")
def api_orders(status: str | None = None):
    orders = load_orders(status=status)
    models = {m["id"]: m for m in load_models()}
    for order in orders:
        model = models.get(order["model_id"])
        order["model_name"] = model["name"] if model else "Modelo removido"
    return orders


@app.post("/api/orders")
def api_create_order(
    code: str = Form(...),
    model_id: str = Form(...),
    quantity: int = Form(...),
    details: str = Form(""),
    art_scale: float = Form(1.0),
    offset_x_mm: float = Form(0.0),
    offset_y_mm: float = Form(0.0),
    art_rotation: int = Form(0),
    artwork: UploadFile = File(...),
):
    if quantity <= 0:
        raise HTTPException(400, "Quantidade deve ser maior que zero")
    try:
        get_model(model_id)
    except KeyError:
        raise HTTPException(404, "Modelo não encontrado")

    suffix = Path(artwork.filename or "arte.png").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "A arte deve ser PNG, JPG, JPEG ou WEBP")

    tmp = temp_upload(artwork)
    try:
        image_path = store_upload(tmp, suffix)
    finally:
        tmp.unlink(missing_ok=True)

    order = {
        "id": uuid.uuid4().hex[:12],
        "code": code.strip(),
        "model_id": model_id,
        "quantity": quantity,
        "details": details.strip(),
        "image_path": image_path,
        "art_scale": max(0.1, min(float(art_scale), 5.0)),
        "offset_x_mm": float(offset_x_mm),
        "offset_y_mm": float(offset_y_mm),
        "art_rotation": int(art_rotation) % 360,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_order(order)
    return order


@app.post("/api/nest")
def api_generate_nest():
    orders = load_orders(status="queued")
    if not orders:
        raise HTTPException(400, "Não há pedidos na fila")

    models = {m["id"]: m for m in load_models()}
    blocks = []
    valid_orders = []
    errors = []

    for order in orders:
        model = models.get(order["model_id"])
        if not model:
            errors.append(f"Pedido {order['code']}: modelo não encontrado")
            continue
        try:
            block = choose_order_block(order, model)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        blocks.append(block)
        valid_orders.append(order)

    if not blocks:
        raise HTTPException(400, "; ".join(errors) or "Nenhum pedido pôde ser montado")

    sheets = pack_order_blocks(blocks)
    block_by_id = {b.order_id: b for b in blocks}
    order_by_id = {o["id"]: o for o in valid_orders}
    order_pdf_paths = {}

    for order in valid_orders:
        model = models[order["model_id"]]
        order_pdf_paths[order["id"]] = build_order_pdf(order, model, block_by_id[order["id"]])

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    outputs = []
    included = set()
    for sheet in sheets:
        filename = f"nest_{batch_id}_folha_{sheet['index']:02d}.pdf"
        path = compose_sheet_pdf(sheet, order_pdf_paths, filename)
        ids = [item["order_id"] for item in sheet["items"]]
        included.update(ids)
        outputs.append(
            {
                "filename": filename,
                "url": f"/output/{filename}",
                "width_mm": sheet["width_mm"],
                "height_mm": round(sheet["height_mm"], 2),
                "utilization": round(sheet["utilization"] * 100, 1),
                "orders": [order_by_id[i]["code"] for i in ids],
            }
        )

    for order_id in included:
        update_order(order_id, status="nested", batch_id=batch_id)

    return {"batch_id": batch_id, "sheets": outputs, "warnings": errors}


@app.get("/output/{filename}")
def download_output(filename: str):
    safe = Path(filename).name
    path = OUTPUT_DIR / safe
    if not path.exists():
        raise HTTPException(404, "Arquivo não encontrado")
    return FileResponse(path, media_type="application/pdf", filename=safe)


INDEX_HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gerador de Impressão Nest</title>
<style>
:root{font-family:Inter,system-ui,Arial,sans-serif;color:#17202a;background:#f4f6f8}*{box-sizing:border-box}body{margin:0}.wrap{max-width:1280px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:18px}.top h1{margin:0;font-size:26px}.muted{color:#667085}.grid{display:grid;grid-template-columns:430px 1fr;gap:18px}.card{background:white;border:1px solid #e4e7ec;border-radius:14px;padding:18px;box-shadow:0 1px 2px #1018280d}.card h2{font-size:17px;margin:0 0 14px}label{display:block;font-size:12px;font-weight:700;margin:11px 0 5px}input,select,textarea,button{font:inherit}input,select,textarea{width:100%;padding:9px 10px;border:1px solid #d0d5dd;border-radius:8px;background:white}textarea{resize:vertical;min-height:60px}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.btn{border:0;border-radius:9px;padding:10px 13px;font-weight:700;cursor:pointer}.primary{background:#17202a;color:white}.secondary{background:#eef2f6;color:#17202a}.danger{background:#fff1f0;color:#b42318}.preview{position:relative;width:100%;height:310px;background:#eef1f4;border:1px dashed #98a2b3;border-radius:10px;overflow:hidden;display:flex;align-items:center;justify-content:center;margin-top:12px}.cut{position:absolute;max-width:86%;max-height:86%;object-fit:contain;z-index:2;pointer-events:none}.art{position:absolute;max-width:none;z-index:1;pointer-events:none;transform-origin:center center}.sliderrow{display:grid;grid-template-columns:80px 1fr 52px;gap:8px;align-items:center;margin-top:8px;font-size:12px}.sliderrow input{padding:0}.queue{width:100%;border-collapse:collapse}.queue th,.queue td{text-align:left;padding:10px 8px;border-bottom:1px solid #eaecf0;font-size:13px}.pill{display:inline-block;padding:3px 8px;border-radius:999px;background:#eef2f6;font-size:11px}.actions{display:flex;gap:8px;flex-wrap:wrap}.sheets{display:grid;gap:10px;margin-top:12px}.sheet{border:1px solid #d0d5dd;border-radius:10px;padding:12px}.ok{background:#ecfdf3;border:1px solid #abefc6;color:#067647;padding:10px;border-radius:8px;margin-top:10px}.err{background:#fef3f2;border:1px solid #fecdca;color:#b42318;padding:10px;border-radius:8px;margin-top:10px}@media(max-width:900px){.grid{grid-template-columns:1fr}.top{align-items:start;flex-direction:column}}
</style>
</head>
<body><div class="wrap">
<div class="top"><div><h1>Gerador de Impressão Nest</h1><div class="muted">Folha 450 mm × altura variável até 600 mm · espaçamento 2 mm</div></div><button class="btn secondary" onclick="toggleModel()">+ Cadastrar modelo</button></div>
<div id="modelCard" class="card" style="display:none;margin-bottom:18px"><h2>Novo modelo</h2><form id="modelForm"><div class="row"><div><label>Nome do produto</label><input name="name" required></div><div class="row"><div><label>Largura (mm)</label><input name="width_mm" type="number" step="0.1" required></div><div><label>Altura (mm)</label><input name="height_mm" type="number" step="0.1" required></div></div></div><label>PDF base do corte</label><input name="cut_pdf" type="file" accept="application/pdf" required><div style="margin-top:12px"><button class="btn primary">Salvar modelo</button></div></form></div>
<div class="grid"><div class="card"><h2>Novo pedido</h2><form id="orderForm"><div class="row"><div><label>Código do pedido</label><input name="code" required></div><div><label>Quantidade</label><input name="quantity" type="number" min="1" value="1" required></div></div><label>Produto</label><select name="model_id" id="modelSelect" required></select><label>Detalhes</label><textarea name="details" placeholder="Opcional"></textarea><label>Arte</label><input name="artwork" id="artInput" type="file" accept="image/png,image/jpeg,image/webp" required><div class="preview" id="preview"><img id="artPreview" class="art"><img id="cutPreview" class="cut"></div><div class="sliderrow"><span>Escala</span><input id="scale" name="art_scale" type="range" min="0.3" max="3" step="0.01" value="1"><span id="scaleV">1.00×</span></div><div class="sliderrow"><span>Horizontal</span><input id="offX" name="offset_x_mm" type="range" min="-80" max="80" step="0.5" value="0"><span id="offXV">0 mm</span></div><div class="sliderrow"><span>Vertical</span><input id="offY" name="offset_y_mm" type="range" min="-80" max="80" step="0.5" value="0"><span id="offYV">0 mm</span></div><input type="hidden" name="art_rotation" value="0"><div class="actions" style="margin-top:12px"><button type="button" class="btn secondary" onclick="resetArt()">Centralizar</button><button class="btn primary">Adicionar à fila</button></div></form><div id="orderMsg"></div></div>
<div class="card"><div style="display:flex;justify-content:space-between;gap:12px;align-items:center"><div><h2 style="margin-bottom:3px">Fila de pedidos</h2><div class="muted" style="font-size:12px">O nest considera todos os pedidos pendentes e procura o melhor encaixe.</div></div><button class="btn primary" onclick="generateNest()">Gerar nest</button></div><div style="overflow:auto;margin-top:10px"><table class="queue"><thead><tr><th>Pedido</th><th>Produto</th><th>Qtd.</th><th>Status</th></tr></thead><tbody id="queueBody"></tbody></table></div><div id="nestMsg"></div><div id="sheets" class="sheets"></div></div></div>
</div>
<script>
let models=[];let artUrl='';
function toggleModel(){const e=document.getElementById('modelCard');e.style.display=e.style.display==='none'?'block':'none'}
async function loadModels(){models=await (await fetch('/api/models')).json();const s=document.getElementById('modelSelect');s.innerHTML=models.length?models.map(m=>`<option value="${m.id}">${m.name} — ${m.width_mm}×${m.height_mm} mm</option>`).join(''):'<option value="">Cadastre um modelo primeiro</option>';updateCutPreview()}
async function loadQueue(){const data=await (await fetch('/api/orders')).json();document.getElementById('queueBody').innerHTML=data.length?data.map(o=>`<tr><td><b>${o.code}</b><br><span class="muted">${o.details||''}</span></td><td>${o.model_name}</td><td>${o.quantity}</td><td><span class="pill">${o.status==='queued'?'na fila':'incluído no nest'}</span></td></tr>`).join(''):'<tr><td colspan="4" class="muted">Nenhum pedido ainda.</td></tr>'}
function currentModel(){return models.find(m=>m.id===document.getElementById('modelSelect').value)}
function updateCutPreview(){const m=currentModel();const img=document.getElementById('cutPreview');if(!m){img.removeAttribute('src');return}img.src=`/api/models/${m.id}/preview?x=${Date.now()}`;applyArt()}
function applyArt(){const m=currentModel();const art=document.getElementById('artPreview');if(!m||!artUrl)return;const box=document.getElementById('preview').getBoundingClientRect();const maxW=box.width*.86,maxH=box.height*.86;const ratio=Math.min(maxW/m.width_mm,maxH/m.height_mm);const scale=parseFloat(document.getElementById('scale').value);const ox=parseFloat(document.getElementById('offX').value)*ratio;const oy=parseFloat(document.getElementById('offY').value)*ratio;const baseW=m.width_mm*ratio*scale;art.style.width=baseW+'px';art.style.left=`calc(50% + ${ox}px)`;art.style.top=`calc(50% + ${oy}px)`;art.style.transform='translate(-50%,-50%)';document.getElementById('scaleV').textContent=scale.toFixed(2)+'×';document.getElementById('offXV').textContent=document.getElementById('offX').value+' mm';document.getElementById('offYV').textContent=document.getElementById('offY').value+' mm'}
function resetArt(){document.getElementById('scale').value=1;document.getElementById('offX').value=0;document.getElementById('offY').value=0;applyArt()}
document.getElementById('modelSelect').addEventListener('change',updateCutPreview);['scale','offX','offY'].forEach(id=>document.getElementById(id).addEventListener('input',applyArt));document.getElementById('artInput').addEventListener('change',e=>{const f=e.target.files[0];if(!f)return;if(artUrl)URL.revokeObjectURL(artUrl);artUrl=URL.createObjectURL(f);document.getElementById('artPreview').src=artUrl;applyArt()});
document.getElementById('modelForm').addEventListener('submit',async e=>{e.preventDefault();const r=await fetch('/api/models',{method:'POST',body:new FormData(e.target)});if(!r.ok){alert((await r.json()).detail||'Erro');return}e.target.reset();toggleModel();await loadModels()});
document.getElementById('orderForm').addEventListener('submit',async e=>{e.preventDefault();const msg=document.getElementById('orderMsg');msg.innerHTML='';const r=await fetch('/api/orders',{method:'POST',body:new FormData(e.target)});if(!r.ok){msg.innerHTML=`<div class="err">${(await r.json()).detail||'Erro ao criar pedido'}</div>`;return}msg.innerHTML='<div class="ok">Pedido adicionado à fila.</div>';e.target.querySelector('[name=code]').value='';e.target.querySelector('[name=quantity]').value=1;e.target.querySelector('[name=details]').value='';e.target.querySelector('[name=artwork]').value='';document.getElementById('artPreview').removeAttribute('src');artUrl='';resetArt();await loadQueue()});
async function generateNest(){const msg=document.getElementById('nestMsg');const sheets=document.getElementById('sheets');msg.innerHTML='<div class="ok">Montando folhas…</div>';sheets.innerHTML='';const r=await fetch('/api/nest',{method:'POST'});const data=await r.json();if(!r.ok){msg.innerHTML=`<div class="err">${data.detail||'Erro ao gerar nest'}</div>`;return}msg.innerHTML=`<div class="ok">Lote ${data.batch_id}: ${data.sheets.length} folha(s) gerada(s).</div>`;sheets.innerHTML=data.sheets.map(s=>`<div class="sheet"><b>${s.filename}</b><div>${s.width_mm} × ${s.height_mm} mm · aproveitamento do retângulo usado: <b>${s.utilization}%</b></div><div class="muted">Pedidos: ${s.orders.join(', ')}</div><div style="margin-top:8px"><a class="btn secondary" href="${s.url}" target="_blank" style="display:inline-block;text-decoration:none">Abrir PDF</a></div></div>`).join('');if(data.warnings?.length)msg.innerHTML+=`<div class="err">${data.warnings.join('<br>')}</div>`;await loadQueue()}
loadModels();loadQueue();window.addEventListener('resize',applyArt);
</script></body></html>'''


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

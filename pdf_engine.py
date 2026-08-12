from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import barcode
import fitz
from barcode.writer import ImageWriter
from PIL import Image, ImageChops

from nest import LABEL_HEIGHT_MM, ORDER_PADDING_MM
from storage import BASE_DIR, OUTPUT_DIR

MM_TO_PT = 72.0 / 25.4
ART_DPI = 300


def mm(value: float) -> float:
    return value * MM_TO_PT


def render_pdf_preview(pdf_path: Path, zoom: float = 2.0) -> bytes:
    doc = fitz.open(pdf_path)
    try:
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True)
        return pix.tobytes("png")
    finally:
        doc.close()


def _barcode_png(value: str) -> bytes:
    stream = io.BytesIO()
    code = barcode.get("code128", value, writer=ImageWriter())
    code.write(
        stream,
        options={
            "write_text": False,
            "module_height": 5.0,
            "module_width": 0.18,
            "quiet_zone": 0.8,
            "dpi": 300,
        },
    )
    return stream.getvalue()


def _cut_mask(template_path: Path, canvas_w: int, canvas_h: int) -> Image.Image:
    """Cria máscara raster da área interna do CutContour.

    Os presets atuais são contornos fechados simples. Renderizamos apenas o traço,
    detectamos os pixels não transparentes e fazemos um flood-fill a partir das
    bordas para distinguir exterior/interior. Assim a impressão fica somente
    dentro da área demarcada, enquanto o CutContour vetorial original continua
    sendo sobreposto depois para a Roland.
    """
    doc = fitz.open(template_path)
    try:
        page = doc[0]
        sx = canvas_w / page.rect.width
        sy = canvas_h / page.rect.height
        pix = page.get_pixmap(matrix=fitz.Matrix(sx, sy), alpha=True)
        rgba = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
        alpha = rgba.getchannel("A")
        if rgba.size != (canvas_w, canvas_h):
            alpha = alpha.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)

        # torna o traço um pouco mais robusto para fechar possíveis anti-alias gaps
        line = alpha.point(lambda p: 255 if p > 12 else 0)
        line = line.filter(__import__("PIL").ImageFilter.MaxFilter(5))

        # Flood-fill do exterior em uma imagem onde o traço é barreira.
        # Pillow floodfill trabalha em L; começamos tudo preto, barreira branca,
        # e marcamos o exterior com 128.
        work = line.copy()
        from PIL import ImageDraw
        # Preenche a partir dos quatro cantos; os pixels de linha (255) bloqueiam.
        for seed in [(0, 0), (canvas_w - 1, 0), (0, canvas_h - 1), (canvas_w - 1, canvas_h - 1)]:
            try:
                ImageDraw.floodfill(work, seed, 128, thresh=0)
            except Exception:
                pass
        # interior = pixels ainda pretos; linha também entra na máscara.
        mask = work.point(lambda p: 0 if p == 128 else 255)
        return mask
    finally:
        doc.close()


def _piece_art_png(
    image_path: Path,
    template_path: Path,
    piece_w_mm: float,
    piece_h_mm: float,
    scale: float,
    offset_x_mm: float,
    offset_y_mm: float,
    rotation: int = 0,
) -> bytes:
    px_per_mm = ART_DPI / 25.4
    canvas_w = max(1, round(piece_w_mm * px_per_mm))
    canvas_h = max(1, round(piece_h_mm * px_per_mm))

    with Image.open(image_path) as original:
        art = original.convert("RGBA")
        if rotation % 360:
            art = art.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)

        iw, ih = art.size
        cover = max(canvas_w / iw, canvas_h / ih)
        resize_factor = cover * max(0.1, scale)
        new_size = (max(1, round(iw * resize_factor)), max(1, round(ih * resize_factor)))
        art = art.resize(new_size, Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 0))
        ox = round(offset_x_mm * px_per_mm)
        oy = round(offset_y_mm * px_per_mm)
        x = (canvas_w - art.width) // 2 + ox
        y = (canvas_h - art.height) // 2 + oy
        canvas.alpha_composite(art, (x, y))

        mask = _cut_mask(template_path, canvas_w, canvas_h)
        current_alpha = canvas.getchannel("A")
        canvas.putalpha(ImageChops.multiply(current_alpha, mask))

        stream = io.BytesIO()
        canvas.save(stream, format="PNG", dpi=(ART_DPI, ART_DPI))
        return stream.getvalue()


def build_order_pdf(order: dict[str, Any], model: dict[str, Any], block: Any) -> Path:
    """Gera um PDF intermediário para um bloco (ou fragmento) de pedido."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"bloco_{block.block_id}.pdf"

    width_pt = mm(block.width_mm)
    height_pt = mm(block.height_mm)
    doc = fitz.open()
    page = doc.new_page(width=width_pt, height=height_pt)

    pad = ORDER_PADDING_MM
    grid_top_mm = pad + LABEL_HEIGHT_MM
    piece_w = block.piece_width_mm
    piece_h = block.piece_height_mm
    spacing = 2.0

    image_path = BASE_DIR / order["image_path"]
    template_path = BASE_DIR / model["pdf_path"]
    template_doc = fitz.open(template_path)

    art_png = _piece_art_png(
        image_path=image_path,
        template_path=template_path,
        piece_w_mm=piece_w,
        piece_h_mm=piece_h,
        scale=float(order.get("art_scale", 1.0)),
        offset_x_mm=float(order.get("offset_x_mm", 0.0)),
        offset_y_mm=float(order.get("offset_y_mm", 0.0)),
        rotation=int(order.get("art_rotation", 0)),
    )

    try:
        for index in range(block.quantity):
            row = index // block.cols
            col = index % block.cols
            x_mm = pad + col * (piece_w + spacing)
            y_mm = grid_top_mm + row * (piece_h + spacing)
            rect = fitz.Rect(mm(x_mm), mm(y_mm), mm(x_mm + piece_w), mm(y_mm + piece_h))

            page.insert_image(rect, stream=art_png, keep_proportion=False)
            page.show_pdf_page(rect, template_doc, 0, keep_proportion=False, overlay=True)

        border = fitz.Rect(mm(0.25), mm(0.25), width_pt - mm(0.25), height_pt - mm(0.25))
        page.draw_rect(border, width=0.25)

        part = ""
        if getattr(block, "part_total", 1) > 1:
            part = f" | PARTE {block.part_index}/{block.part_total}"
        info = f"PED {order['code']} | {model['name']} | QTD BLOCO {block.quantity}/{order['quantity']}{part}"
        details = (order.get("details") or "").strip()
        if details:
            info += f" | {details}"
        page.insert_text((mm(pad), mm(4.0)), info[:160], fontsize=5.3)

        barcode_bytes = _barcode_png(str(order["code"]))
        barcode_rect = fitz.Rect(width_pt - mm(38), mm(1.0), width_pt - mm(2), mm(8.2))
        page.insert_image(barcode_rect, stream=barcode_bytes, keep_proportion=True)
        page.insert_text((width_pt - mm(37), mm(9.3)), str(order["code"]), fontsize=4.5)

        doc.save(out, garbage=4, deflate=True)
    finally:
        template_doc.close()
        doc.close()
    return out


def _append_sheet_page(doc: fitz.Document, sheet: dict[str, Any], block_pdf_paths: dict[str, Path]) -> None:
    page = doc.new_page(width=mm(sheet["width_mm"]), height=mm(sheet["height_mm"]))
    opened: list[fitz.Document] = []
    try:
        for item in sheet["items"]:
            src = fitz.open(block_pdf_paths[item["block_id"]])
            opened.append(src)
            target = fitz.Rect(
                mm(item["x_mm"]),
                mm(item["y_mm"]),
                mm(item["x_mm"] + item["width_mm"]),
                mm(item["y_mm"] + item["height_mm"]),
            )
            # O bloco externo nunca gira: 450 mm é a largura fixa da máquina.
            page.show_pdf_page(target, src, 0, rotate=0, keep_proportion=False, overlay=True)
    finally:
        for src in opened:
            src.close()


def compose_batch_pdf(sheets: list[dict[str, Any]], block_pdf_paths: dict[str, Path], output_name: str) -> Path:
    """Gera UM ÚNICO PDF, com uma página para cada folha de impressão."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / output_name
    doc = fitz.open()
    try:
        for sheet in sheets:
            _append_sheet_page(doc, sheet, block_pdf_paths)
        doc.save(out, garbage=4, deflate=True)
    finally:
        doc.close()
    return out


def compose_sheet_pdf(sheet: dict[str, Any], block_pdf_paths: dict[str, Path], output_name: str) -> Path:
    """Mantido por compatibilidade; gera somente uma página."""
    return compose_batch_pdf([sheet], block_pdf_paths, output_name)

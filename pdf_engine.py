from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import barcode
import fitz
from barcode.writer import ImageWriter
from PIL import Image

from nest import LABEL_HEIGHT_MM, ORDER_PADDING_MM
from storage import BASE_DIR, OUTPUT_DIR

MM_TO_PT = 72.0 / 25.4


def mm(value: float) -> float:
    return value * MM_TO_PT


def render_pdf_preview(pdf_path: Path, zoom: float = 2.0) -> bytes:
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return pix.tobytes("png")


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


def _insert_art(page: fitz.Page, rect: fitz.Rect, image_path: Path, scale: float, offset_x_mm: float, offset_y_mm: float, rotation: int = 0) -> None:
    with Image.open(image_path) as img:
        iw, ih = img.size
    if iw <= 0 or ih <= 0:
        return

    target_w = rect.width * scale
    target_h = target_w * ih / iw
    if target_h < rect.height * scale:
        target_h = rect.height * scale
        target_w = target_h * iw / ih

    cx = (rect.x0 + rect.x1) / 2 + mm(offset_x_mm)
    cy = (rect.y0 + rect.y1) / 2 + mm(offset_y_mm)
    art_rect = fitz.Rect(cx - target_w / 2, cy - target_h / 2, cx + target_w / 2, cy + target_h / 2)
    page.insert_image(art_rect, filename=str(image_path), keep_proportion=True, rotate=rotation)


def build_order_pdf(order: dict[str, Any], model: dict[str, Any], block: Any) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"pedido_{order['code']}_{order['id']}.pdf"

    width_pt = mm(block.width_mm)
    height_pt = mm(block.height_mm)
    doc = fitz.open()
    page = doc.new_page(width=width_pt, height=height_pt)

    pad = ORDER_PADDING_MM
    label_h = LABEL_HEIGHT_MM
    grid_top_mm = pad + label_h
    piece_w = block.piece_width_mm
    piece_h = block.piece_height_mm
    spacing = 2.0

    image_path = BASE_DIR / order["image_path"]
    template_path = BASE_DIR / model["pdf_path"]
    template_doc = fitz.open(template_path)

    for index in range(block.quantity):
        row = index // block.cols
        col = index % block.cols
        x_mm = pad + col * (piece_w + spacing)
        y_mm = grid_top_mm + row * (piece_h + spacing)
        rect = fitz.Rect(mm(x_mm), mm(y_mm), mm(x_mm + piece_w), mm(y_mm + piece_h))

        _insert_art(
            page,
            rect,
            image_path,
            float(order.get("art_scale", 1.0)),
            float(order.get("offset_x_mm", 0.0)),
            float(order.get("offset_y_mm", 0.0)),
            int(order.get("art_rotation", 0)),
        )
        page.show_pdf_page(rect, template_doc, 0, keep_proportion=False, overlay=True)

    border = fitz.Rect(mm(0.25), mm(0.25), width_pt - mm(0.25), height_pt - mm(0.25))
    page.draw_rect(border, width=0.25)

    info = f"PED {order['code']} | {model['name']} | QTD {order['quantity']}"
    details = (order.get("details") or "").strip()
    if details:
        info += f" | {details}"
    page.insert_text((mm(pad), mm(4.0)), info[:140], fontsize=5.5)

    barcode_bytes = _barcode_png(str(order["code"]))
    barcode_rect = fitz.Rect(width_pt - mm(38), mm(1.0), width_pt - mm(2), mm(8.5))
    page.insert_image(barcode_rect, stream=barcode_bytes, keep_proportion=True)
    page.insert_text((width_pt - mm(37), mm(9.4)), str(order["code"]), fontsize=4.5)

    doc.save(out, garbage=4, deflate=True)
    doc.close()
    template_doc.close()
    return out


def compose_sheet_pdf(sheet: dict[str, Any], order_pdf_paths: dict[str, Path], output_name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / output_name
    doc = fitz.open()
    page = doc.new_page(width=mm(sheet["width_mm"]), height=mm(sheet["height_mm"]))

    opened: list[fitz.Document] = []
    try:
        for item in sheet["items"]:
            src = fitz.open(order_pdf_paths[item["order_id"]])
            opened.append(src)
            target = fitz.Rect(
                mm(item["x_mm"]),
                mm(item["y_mm"]),
                mm(item["x_mm"] + item["width_mm"]),
                mm(item["y_mm"] + item["height_mm"]),
            )
            rotate = 90 if item["rotated"] else 0
            page.show_pdf_page(target, src, 0, rotate=rotate, keep_proportion=False, overlay=True)
        doc.save(out, garbage=4, deflate=True)
    finally:
        for src in opened:
            src.close()
        doc.close()
    return out

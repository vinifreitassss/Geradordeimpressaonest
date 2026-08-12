from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from rectpack import newPacker, MaxRectsBssf, PackingMode, SORT_AREA

SHEET_WIDTH_MM = 450.0
SHEET_MAX_HEIGHT_MM = 600.0
PIECE_SPACING_MM = 2.0
LABEL_HEIGHT_MM = 10.0
ORDER_PADDING_MM = 2.0


@dataclass
class OrderBlock:
    order_id: str
    width_mm: float
    height_mm: float
    cols: int
    rows: int
    piece_width_mm: float
    piece_height_mm: float
    quantity: int


def _block_dimensions(quantity: int, piece_w: float, piece_h: float, cols: int) -> tuple[float, float, int]:
    rows = math.ceil(quantity / cols)
    grid_w = cols * piece_w + max(0, cols - 1) * PIECE_SPACING_MM
    grid_h = rows * piece_h + max(0, rows - 1) * PIECE_SPACING_MM
    return (
        grid_w + 2 * ORDER_PADDING_MM,
        grid_h + LABEL_HEIGHT_MM + 2 * ORDER_PADDING_MM,
        rows,
    )


def choose_order_block(order: dict[str, Any], model: dict[str, Any]) -> OrderBlock:
    quantity = int(order["quantity"])
    candidates: list[tuple[float, float, int, int, float, float]] = []

    orientations = [
        (float(model["width_mm"]), float(model["height_mm"])),
        (float(model["height_mm"]), float(model["width_mm"])),
    ]

    seen: set[tuple[float, float]] = set()
    for piece_w, piece_h in orientations:
        if (piece_w, piece_h) in seen:
            continue
        seen.add((piece_w, piece_h))
        for cols in range(1, quantity + 1):
            block_w, block_h, rows = _block_dimensions(quantity, piece_w, piece_h, cols)
            if block_w <= SHEET_WIDTH_MM and block_h <= SHEET_MAX_HEIGHT_MM:
                area = block_w * block_h
                compactness = max(block_w / SHEET_WIDTH_MM, block_h / SHEET_MAX_HEIGHT_MM)
                candidates.append((area, compactness, cols, rows, piece_w, piece_h))

    if not candidates:
        raise ValueError(
            f"Pedido {order['code']} não cabe em uma folha de {SHEET_WIDTH_MM:.0f}x{SHEET_MAX_HEIGHT_MM:.0f} mm como bloco único."
        )

    candidates.sort(key=lambda x: (x[0], x[1]))
    _, _, cols, rows, piece_w, piece_h = candidates[0]
    block_w, block_h, _ = _block_dimensions(quantity, piece_w, piece_h, cols)
    return OrderBlock(
        order_id=order["id"],
        width_mm=block_w,
        height_mm=block_h,
        cols=cols,
        rows=rows,
        piece_width_mm=piece_w,
        piece_height_mm=piece_h,
        quantity=quantity,
    )


def pack_order_blocks(blocks: list[OrderBlock]) -> list[dict[str, Any]]:
    if not blocks:
        return []

    scale = 100  # centésimo de mm para o empacotador inteiro
    packer = newPacker(
        mode=PackingMode.Offline,
        pack_algo=MaxRectsBssf,
        sort_algo=SORT_AREA,
        rotation=True,
    )

    for block in blocks:
        packer.add_rect(
            int(round(block.width_mm * scale)),
            int(round(block.height_mm * scale)),
            rid=block.order_id,
        )

    for _ in range(len(blocks)):
        packer.add_bin(
            int(round(SHEET_WIDTH_MM * scale)),
            int(round(SHEET_MAX_HEIGHT_MM * scale)),
            count=1,
        )

    packer.pack()
    by_id = {b.order_id: b for b in blocks}
    sheets: dict[int, dict[str, Any]] = {}

    for bin_index, x, y, w, h, rid in packer.rect_list():
        sheet = sheets.setdefault(bin_index, {"items": [], "used_height_mm": 0.0})
        original = by_id[rid]
        placed_w = w / scale
        placed_h = h / scale
        rotated = not (
            abs(placed_w - original.width_mm) < 0.02
            and abs(placed_h - original.height_mm) < 0.02
        )
        item = {
            "order_id": rid,
            "x_mm": x / scale,
            "y_mm": y / scale,
            "width_mm": placed_w,
            "height_mm": placed_h,
            "rotated": rotated,
            "block": original,
        }
        sheet["items"].append(item)
        sheet["used_height_mm"] = max(sheet["used_height_mm"], item["y_mm"] + item["height_mm"])

    result = []
    for index in sorted(sheets):
        sheet = sheets[index]
        used_area = sum(i["width_mm"] * i["height_mm"] for i in sheet["items"])
        used_height = max(1.0, sheet["used_height_mm"])
        utilization = used_area / (SHEET_WIDTH_MM * used_height)
        result.append(
            {
                "index": index + 1,
                "width_mm": SHEET_WIDTH_MM,
                "height_mm": min(SHEET_MAX_HEIGHT_MM, used_height),
                "utilization": utilization,
                "items": sheet["items"],
            }
        )
    return result

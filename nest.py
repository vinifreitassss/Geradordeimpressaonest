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
LARGE_ORDER_FRAGMENT_ROWS = 3


@dataclass
class OrderBlock:
    block_id: str
    order_id: str
    width_mm: float
    height_mm: float
    cols: int
    rows: int
    piece_width_mm: float
    piece_height_mm: float
    quantity: int
    part_index: int = 1
    part_total: int = 1


def _block_dimensions(quantity: int, piece_w: float, piece_h: float, cols: int) -> tuple[float, float, int]:
    rows = math.ceil(quantity / cols)
    used_cols = min(quantity, cols)
    grid_w = used_cols * piece_w + max(0, used_cols - 1) * PIECE_SPACING_MM
    grid_h = rows * piece_h + max(0, rows - 1) * PIECE_SPACING_MM
    return (
        grid_w + 2 * ORDER_PADDING_MM,
        grid_h + LABEL_HEIGHT_MM + 2 * ORDER_PADDING_MM,
        rows,
    )


def _horizontal_layout(quantity: int, model: dict[str, Any], max_rows: int | None = None) -> tuple[int, int, float, float, float, float] | None:
    orientations = [
        (float(model["width_mm"]), float(model["height_mm"])),
        (float(model["height_mm"]), float(model["width_mm"])),
    ]
    seen: set[tuple[float, float]] = set()
    candidates = []

    for piece_w, piece_h in orientations:
        key = (round(piece_w, 4), round(piece_h, 4))
        if key in seen:
            continue
        seen.add(key)
        max_cols = max(1, int((SHEET_WIDTH_MM - 2 * ORDER_PADDING_MM + PIECE_SPACING_MM) // (piece_w + PIECE_SPACING_MM)))
        cols = min(quantity, max_cols)
        block_w, block_h, rows = _block_dimensions(quantity, piece_w, piece_h, cols)
        if max_rows is not None and rows > max_rows:
            continue
        if block_w <= SHEET_WIDTH_MM + 1e-6 and block_h <= SHEET_MAX_HEIGHT_MM + 1e-6:
            candidates.append((block_h, -block_w, -cols, cols, rows, piece_w, piece_h))

    if not candidates:
        return None
    candidates.sort()
    _, _, _, cols, rows, piece_w, piece_h = candidates[0]
    block_w, block_h, _ = _block_dimensions(quantity, piece_w, piece_h, cols)
    return cols, rows, piece_w, piece_h, block_w, block_h


def _make_block(order: dict[str, Any], qty: int, layout: tuple[int, int, float, float, float, float], block_id: str) -> OrderBlock:
    cols, rows, piece_w, piece_h, block_w, block_h = layout
    return OrderBlock(
        block_id=block_id,
        order_id=order["id"],
        width_mm=block_w,
        height_mm=block_h,
        cols=cols,
        rows=rows,
        piece_width_mm=piece_w,
        piece_height_mm=piece_h,
        quantity=qty,
    )


def choose_order_block(order: dict[str, Any], model: dict[str, Any], quantity: int | None = None, block_id: str | None = None) -> OrderBlock:
    qty = int(quantity if quantity is not None else order["quantity"])
    layout = _horizontal_layout(qty, model)
    if layout is None:
        raise ValueError(
            f"Pedido {order['code']} não cabe em uma folha de {SHEET_WIDTH_MM:.0f}x{SHEET_MAX_HEIGHT_MM:.0f} mm como bloco único."
        )
    return _make_block(order, qty, layout, block_id or order["id"])


def split_order_blocks(order: dict[str, Any], model: dict[str, Any]) -> list[OrderBlock]:
    total_qty = int(order["quantity"])
    whole_layout = _horizontal_layout(total_qty, model)
    if whole_layout is not None:
        return [_make_block(order, total_qty, whole_layout, order["id"])]

    # Procura a maior quantidade que caiba em um fragmento baixo/horizontal.
    fragment_capacity = 0
    max_probe = total_qty
    for qty in range(1, max_probe + 1):
        if _horizontal_layout(qty, model, max_rows=LARGE_ORDER_FRAGMENT_ROWS) is not None:
            fragment_capacity = qty
        else:
            # depois que ultrapassa a capacidade das 3 linhas, quantidades maiores
            # também não voltarão a caber neste limite.
            if fragment_capacity:
                break

    if fragment_capacity <= 0:
        raise ValueError(f"Pedido {order['code']}: a peça não cabe na área útil de 450x600 mm.")

    quantities = []
    remaining = total_qty
    while remaining > 0:
        q = min(fragment_capacity, remaining)
        layout = _horizontal_layout(q, model, max_rows=LARGE_ORDER_FRAGMENT_ROWS)
        while q > 0 and layout is None:
            q -= 1
            layout = _horizontal_layout(q, model, max_rows=LARGE_ORDER_FRAGMENT_ROWS)
        if q <= 0 or layout is None:
            raise ValueError(f"Pedido {order['code']}: não foi possível criar um bloco de produção válido.")
        quantities.append((q, layout))
        remaining -= q

    blocks: list[OrderBlock] = []
    part_total = len(quantities)
    for idx, (qty, layout) in enumerate(quantities, start=1):
        block = _make_block(order, qty, layout, f"{order['id']}__{idx:03d}")
        block.part_index = idx
        block.part_total = part_total
        blocks.append(block)
    return blocks


def pack_order_blocks(blocks: list[OrderBlock]) -> list[dict[str, Any]]:
    if not blocks:
        return []

    scale = 100
    packer = newPacker(
        mode=PackingMode.Offline,
        pack_algo=MaxRectsBssf,
        sort_algo=SORT_AREA,
        rotation=False,
    )

    for block in blocks:
        packer.add_rect(
            int(round(block.width_mm * scale)),
            int(round(block.height_mm * scale)),
            rid=block.block_id,
        )

    for _ in range(len(blocks)):
        packer.add_bin(
            int(round(SHEET_WIDTH_MM * scale)),
            int(round(SHEET_MAX_HEIGHT_MM * scale)),
            count=1,
        )

    packer.pack()
    by_id = {b.block_id: b for b in blocks}
    sheets: dict[int, dict[str, Any]] = {}

    for bin_index, x, y, w, h, rid in packer.rect_list():
        sheet = sheets.setdefault(bin_index, {"items": [], "used_height_mm": 0.0})
        original = by_id[rid]
        item = {
            "block_id": rid,
            "order_id": original.order_id,
            "x_mm": x / scale,
            "y_mm": y / scale,
            "width_mm": w / scale,
            "height_mm": h / scale,
            "rotated": False,
            "block": original,
        }
        sheet["items"].append(item)
        sheet["used_height_mm"] = max(sheet["used_height_mm"], item["y_mm"] + item["height_mm"])

    placed_ids = {item["block_id"] for sheet in sheets.values() for item in sheet["items"]}
    missing = [b.block_id for b in blocks if b.block_id not in placed_ids]
    if missing:
        raise ValueError(f"{len(missing)} bloco(s) não puderam ser encaixados nas folhas.")

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

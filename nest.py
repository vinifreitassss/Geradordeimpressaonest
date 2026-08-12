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
# Pedidos que não cabem inteiros são quebrados em blocos horizontais de até 3 linhas.
# Isso dá flexibilidade ao nest para preencher a mesma folha com outros pedidos.
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
    grid_w = min(quantity, cols) * piece_w + max(0, min(quantity, cols) - 1) * PIECE_SPACING_MM
    grid_h = rows * piece_h + max(0, rows - 1) * PIECE_SPACING_MM
    return (
        grid_w + 2 * ORDER_PADDING_MM,
        grid_h + LABEL_HEIGHT_MM + 2 * ORDER_PADDING_MM,
        rows,
    )


def _horizontal_layout(quantity: int, model: dict[str, Any], max_rows: int | None = None) -> tuple[int, int, float, float, float, float] | None:
    """Escolhe a montagem mais horizontal possível.

    A largura de 450 mm é a referência fixa da impressora. Por isso priorizamos
    mais colunas e menor altura, em vez de procurar o retângulo de menor área.
    A peça em si pode ser girada 90 graus quando isso permitir uma grade melhor.
    """
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
        if cols < 1:
            continue
        block_w, block_h, rows = _block_dimensions(quantity, piece_w, piece_h, cols)
        if max_rows is not None and rows > max_rows:
            continue
        if block_w <= SHEET_WIDTH_MM + 1e-6 and block_h <= SHEET_MAX_HEIGHT_MM + 1e-6:
            # Menor altura primeiro; empate: maior largura/mais colunas.
            candidates.append((block_h, -block_w, -cols, cols, rows, piece_w, piece_h))

    if not candidates:
        return None
    candidates.sort()
    _, _, _, cols, rows, piece_w, piece_h = candidates[0]
    block_w, block_h, _ = _block_dimensions(quantity, piece_w, piece_h, cols)
    return cols, rows, piece_w, piece_h, block_w, block_h


def choose_order_block(order: dict[str, Any], model: dict[str, Any], quantity: int | None = None, block_id: str | None = None) -> OrderBlock:
    qty = int(quantity if quantity is not None else order["quantity"])
    layout = _horizontal_layout(qty, model)
    if layout is None:
        raise ValueError(
            f"Pedido {order['code']} não cabe em uma folha de {SHEET_WIDTH_MM:.0f}x{SHEET_MAX_HEIGHT_MM:.0f} mm como bloco único."
        )
    cols, rows, piece_w, piece_h, block_w, block_h = layout
    return OrderBlock(
        block_id=block_id or order["id"],
        order_id=order["id"],
        width_mm=block_w,
        height_mm=block_h,
        cols=cols,
        rows=rows,
        piece_width_mm=piece_w,
        piece_height_mm=piece_h,
        quantity=qty,
    )


def split_order_blocks(order: dict[str, Any], model: dict[str, Any]) -> list[OrderBlock]:
    """Mantém pedidos pequenos inteiros e fragmenta automaticamente os grandes.

    Fragmentos são deliberadamente horizontais e relativamente baixos para que
    o MaxRects consiga misturá-los com pedidos menores na mesma folha.
    """
    total_qty = int(order["quantity"])
    whole_layout = _horizontal_layout(total_qty, model)
    if whole_layout is not None:
        return [choose_order_block(order, model)]

    # Descobre quantas peças cabem em um fragmento horizontal de até N linhas.
    orientations = [
        (float(model["width_mm"]), float(model["height_mm"])),
        (float(model["height_mm"]), float(model["width_mm"])),
    ]
    fragment_candidates: list[tuple[int, float, float]] = []
    seen: set[tuple[float, float]] = set()
    for piece_w, piece_h in orientations:
        key = (round(piece_w, 4), round(piece_h, 4))
        if key in seen:
            continue
        seen.add(key)
        max_cols = int((SHEET_WIDTH_MM - 2 * ORDER_PADDING_MM + PIECE_SPACING_MM) // (piece_w + PIECE_SPACING_MM))
        if max_cols < 1:
            continue
        max_rows_sheet = int((SHEET_MAX_HEIGHT_MM - LABEL_HEIGHT_MM - 2 * ORDER_PADDING_MM + PIECE_SPACING_MM) // (piece_h + PIECE_SPACING_MM))
        rows = min(LARGE_ORDER_FRAGMENT_ROWS, max_rows_sheet)
        if rows < 1:
            continue
        fragment_candidates.append((max_cols * rows, piece_w, piece_h))

    if not fragment_candidates:
        raise ValueError(f"Pedido {order['code']}: a peça não cabe na área útil de 450x600 mm.")

    # Prioriza maior capacidade por fragmento; o layout final continua horizontal.
    fragment_candidates.sort(key=lambda x: x[0], reverse=True)
    fragment_capacity = fragment_candidates[0][0]
    quantities = []
    remaining = total_qty
    while remaining > 0:
        q = min(fragment_capacity, remaining)
        # Caso excepcional: diminui até achar uma montagem válida.
        while q > 0 and _horizontal_layout(q, model, max_rows=LARGE_ORDER_FRAGMENT_ROWS) is None:
            q -= 1
        if q <= 0:
            raise ValueError(f"Pedido {order['code']}: não foi possível criar um bloco de produção válido.")
        quantities.append(q)
        remaining -= q

    blocks: list[OrderBlock] = []
    part_total = len(quantities)
    for idx, qty in enumerate(quantities, start=1):
        block = choose_order_block(order, model, quantity=qty, block_id=f"{order['id']}__{idx:03d}")
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
        # IMPORTANTE: o bloco do pedido não gira. A largura de 450 mm é fixa
        # no sentido de alimentação da Roland. A rotação da peça é decidida
        # internamente na montagem do bloco, nunca pelo nest externo.
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

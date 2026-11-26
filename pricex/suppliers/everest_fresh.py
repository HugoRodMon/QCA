"""Everest Fresh: pdf with one grid per species, prices under 'Size N' headings.

    Oranges TC                                                               <- section
    Variety  Origin Brand Content Pack Box pp Cat Size 48 Size 56 Size 64    <- header with sizes
    Valencia RSA    Various 15kg  TC   80pp   1   EXP     € 13,00 € 13,00
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._pdf import Columns, nearest, price_cells

BASE = ["Origin", "Brand", "Content", "Pack", "Box pp", "Cat"]


@register
class EverestFresh(Supplier):
    name = "Everest Fresh"
    final_file = "EVEREST FRESH.xlsx"
    match_names = ["everest"]
    match_text = ["everestfresh", "everest fresh"]
    layout_hints = [r"origin brand content pack box pp cat size"]
    layout = "wide"
    origin_style = "source"
    origin_overrides = {"Brazil": "Brazil", "Peru": "Peru", "Chile": "Chile", "Costa Rica": "Costa Rica"}
    sheet_names = {"Watermelons": "Melons"}

    def parse(self, doc):
        rows, section, cols, sizes = [], "", None, []
        for line in doc.lines:
            texts = [w.text for w in line.words]
            if "Origin" in texts and "Cat" in texts:
                cols = Columns.from_header(line, BASE)
                cols.starts.insert(0, ("Product", 0))
                sizes = size_headers(line)
                continue
            if cols is None:
                continue
            if len(line.words) <= 2 and not any(c.isdigit() for c in line.text):
                if line.text.lower().startswith("contact"):
                    break
                section = line.text
                continue
            grid_x = min(x for _, x in sizes) - 6 if sizes else 10_000
            base_line = type(line)([w for w in line.words if w.x0 < grid_x], line.page)
            c = cols.split(base_line)
            if not c.get("Product") or not sizes:
                continue
            for cell in price_cells([w for w in line.words if w.x0 >= grid_x]):
                if cell["price"] is None:
                    continue
                i = nearest(cell["x0"], [x for _, x in sizes], max_dist=15)
                if i is None:
                    continue
                product = re.sub(r"[()]", "", c["Product"])
                rows.append(self.row(
                    specie=f"{product} {section}", variety=product, origin=c["Origin"],
                    brand=c["Brand"], weight=N.parse_weight(c["Content"]),
                    detail=N.box_type(c["Pack"]), box_pp=N.to_number(c["Box pp"]),
                    cat=N.to_number(c["Cat"]), size=sizes[i][0], price=cell["price"], not_final=cell.get("red", False)))
        return rows


def size_headers(line):
    """[(size, x)] from 'Size 48 Size 56 ...' or '16 mm'."""
    out = []
    words = line.words
    cat_x = next(w.x1 for w in words if w.text == "Cat")
    i = 0
    while i < len(words):
        w = words[i]
        if w.x0 > cat_x:
            if w.text == "Size" and i + 1 < len(words):
                out.append((words[i + 1].text, w.x0))
                i += 2
                continue
            if w.text.startswith("Size") and len(w.text) > 4:          # "Size1XXX" glued
                out.append((w.text[4:], w.x0))
            elif re.fullmatch(r"\d+", w.text) and i + 1 < len(words) and words[i + 1].text == "mm":
                out.append((w.text + "+", w.x0))
                i += 2
                continue
        i += 1
    return out

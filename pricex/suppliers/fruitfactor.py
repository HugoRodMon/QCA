"""Fruitfactor: pdf where every product block has its own size heading.

    Product  Origin Brand  Box pp Packing Weight  Size & Price in € Euro      <- page header
    Citrus                                                                    <- section
    Oranges                              48      56     64                    <- size heading (+ label)
    Cambria  RSA           80  Carton  15kg  € 12,00 € 12,00                  <- product row
                   CAT II                                                     <- small line under it
                                     Mix 20/22                                <- size headings can use 2 lines
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._common import remove_alias
from ._pdf import nearest, price_cells


@register
class Fruitfactor(Supplier):
    name = "Fruitfactor"
    final_file = "Fruitfactor.xlsx"
    match_names = ["fruitfactor", "fruit factor"]
    match_text = ["fruitfactor", "59687789", "bieslookweg"]   # name, CoC number, address
    layout_hints = [r"product origin brand box pp packing weight size & price"]
    layout = "wide"
    origin_style = "name"

    def parse(self, doc):
        rows = []
        x = None                    # column borders from the page header
        section, label, sizes = "", "", []
        last_was_sizes = False
        last_rows = []
        for line in doc.lines:
            texts = [w.text for w in line.words]
            if "Product" in texts and "Origin" in texts:
                pos = {w.text: w.x0 for w in line.words}
                x = {"origin": pos["Origin"] - 6, "brand": pos["Brand"] - 3, "pp": pos["Box"] - 12,
                     "packing": pos["Packing"] - 3, "weight": pos["Weight"] - 3, "grid": pos["Weight"] + 18}
                continue
            if x is None:
                continue
            left = [w for w in line.words if w.x0 < x["origin"]]
            grid = [w for w in line.words if x["grid"] <= w.x0 < 535]
            middle = [w for w in line.words if x["origin"] <= w.x0 < x["grid"]]

            if not middle and grid and all(is_size_word(w.text) for w in grid):      # size heading
                new = size_headers(grid)
                sizes = sizes + new if last_was_sizes else new
                if left:
                    label = " ".join(w.text for w in left)
                last_was_sizes = True
                continue
            last_was_sizes = False

            if left and not middle and not grid:                                     # section / group
                text = " ".join(w.text for w in left)
                if text.lower().startswith("prices are"):
                    break
                if line.size >= 7:
                    section, label = text, ""
                else:
                    label = text
                continue

            if not left and middle and line.size < 7:                                # note under a product
                note = " ".join(w.text for w in middle)
                for r in last_rows:
                    if re.fullmatch(r"(?i)cat\.?\s*(ii|2)", note):
                        r.cat = 2
                    elif re.search(r"(?i)label|price per", note):
                        r.detail = " ".join(v for v in (r.detail, note) if v)
                    else:
                        r.brand = note
                continue

            if not (left and middle):
                continue
            last_rows = self.product_rows(line, x, left, grid, section, label, sizes)
            rows += last_rows
        return rows

    def product_rows(self, line, x, left, grid, section, label, sizes):
        def between(a, b):
            return " ".join(w.text for w in line.words if x[a] <= w.x0 < x[b])

        product = " ".join(w.text for w in left)
        type_ = ""
        for q in re.findall(r'"([^"]*)"?', product):
            type_ = q.strip()
        product = re.sub(r'"[^"]*"?', "", product).strip()
        pack = N.pack_detail(product) or ""
        species = N.find_species(f"{product} {label} {section}") or N.species_from_variety(product)
        variety = re.sub(r"(?i)\b(with|without) label\b", "", product).strip()
        if pack:
            variety = re.sub(r"(?i)\d+\s*x\s*\d+\s*(gram|gr|g)?", "", variety).strip()
        if species:
            variety = remove_alias(variety, species)
        label_detail = re.search(r"(?i)\b(with|without) label\b", product)
        out = []
        for cell in price_cells(grid):
            if cell["price"] is None:
                continue
            i = nearest(cell["x0"], [sx for _, sx in sizes], max_dist=22)
            if i is None:
                continue
            size = sizes[i][0]
            size_pack = N.pack_detail(size)
            if size_pack:
                size = "N/S"
            out.append(self.row(
                specie=species or f"{product} {label} {section}", variety=variety,
                origin=between("origin", "brand"), brand=between("brand", "pp"),
                box_pp=N.to_number(between("pp", "packing")),
                packaging=N.packaging_from(between("packing", "weight")),
                weight=N.parse_weight(between("weight", "grid")), size=size, price=cell["price"],
                detail=" ".join(v for v in (pack or size_pack, label_detail[0] if label_detail else "",
                                            "By Air" if "by air" in type_.lower() else "") if v),
                type=type_ if "by air" not in type_.lower() else ""))
        return out


def is_size_word(t):
    # grapes use J, JJ, 2J, XXL besides S/M/L/XL
    return bool(re.fullmatch(r"(?i)mix[\d/]*|[\d/]+\+?|\d+mm\+|\d+x\d+(kg|g)?|[smlx]{1,3}|\d?j{1,2}|x{0,2}l", t))


def size_headers(words):
    """'Mix' followed by '20/22' is one heading; 'Mix14/16/18' -> 'Mix 14/16/18'."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        t, x0 = w.text, w.x0
        if t.lower() == "mix" and i + 1 < len(words):
            t = "Mix " + words[i + 1].text
            i += 1
        elif t.lower().startswith("mix") and len(t) > 3:
            t = "Mix " + t[3:]
        out.append((t, x0 + 4))
        i += 1
    return out

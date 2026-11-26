"""Olympic Fruit: pdf, one block per product group with its own size line.

    Oranges            Origin Brand  Contains Cat. Package Boxes  Type   ETA     <- group header
                                                            A1052                <- article code (ignored)
                                                            48  56  64  72       <- sizes
    Valencia/Midknight RSA  Multiple 15,0kg   I    Carton  80p.p. Telescope € 14,00 POR. € 14,00
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._pdf import Columns, nearest, price_cells

BASE = ["Origin", "Brand", "Contains", "Cat.", "Package", "Boxes", "Type", "ETA"]
TYPES = {"telescope": "Telescopic", "open top": "Open Top"}


@register
class Olympic(Supplier):
    name = "Olympic"
    final_file = "OLYMPIC.xlsx"
    match_names = ["olympic"]
    match_text = ["olympic fruit", "olympicfruit"]
    layout_hints = [r"origin brand contains cat\. package boxes type"]
    layout = "wide"
    origin_style = "NAME"
    upper_species = True
    default_packaging = "CARTON"
    species_names = {"Kiwis": "KIWIS"}
    sheet_names = {"Peaches": "STONEFRUITS", "Nectarines": "STONEFRUITS", "Apricots": "STONEFRUITS"}

    def parse(self, doc):
        rows, group, cols, sizes, grid_x = [], "", None, [], 10_000
        for line in doc.lines:
            texts = [w.text for w in line.words]
            if "Origin" in texts and "Contains" in texts:
                cols = Columns.from_header(line, BASE)
                cols.starts.insert(0, ("Product", 0))
                group = " ".join(w.text for w in line.words if w.x0 < cols.starts[1][1] - 5)
                grid_x = dict(cols.starts)["Type"] + 45
                continue
            if cols is None:
                continue
            if line.text.upper().startswith("CONTACT"):
                break
            words = [w for w in line.words if not re.fullmatch(r"[A-Z]\d{4}", w.text)]   # article codes
            if not words:
                continue
            if all(w.x0 >= grid_x for w in words) and line.size < 9:                     # size line
                sizes = [(w.text, w.x0) for w in words]
                continue
            base = type(line)([w for w in words if w.x0 < grid_x], line.page)
            c = cols.split(base)
            if not c["Product"] or not c["Origin"]:
                continue
            for cell in price_cells([w for w in words if grid_x <= w.x0 < dict(cols.starts)["ETA"] - 5]):
                if cell["price"] is None or not sizes:
                    continue
                i = nearest(cell["x0"] + 6, [x for _, x in sizes], max_dist=20)
                if i is None:
                    continue
                size, detail = sizes[i][0], TYPES.get(c["Type"].lower(), c["Type"])
                if size.lower() in ("unlabeled", "labeled"):
                    size, detail = "N/S", " ".join(x for x in (detail, size) if x)
                # "Valencia/Midknight" or "Arra15/Bebop": same price for each variety
                for variety in re.split(r"\s*/\s*", c["Product"]):
                    rows.append(self.row(
                        specie=f"{variety} {group}", variety=re.sub(r"(?<=[a-z])(\d)", r" \1", variety),
                        origin=c["Origin"], brand=c["Brand"], weight=N.parse_weight(c["Contains"]),
                        cat=1 if c["Cat."] == "I" else 2 if c["Cat."] == "II" else c["Cat."],
                        packaging=c["Package"].upper(), box_pp=N.to_number(c["Boxes"]),
                        detail=detail, size=size, price=cell["price"], not_final=cell.get("red", False)))
        return rows

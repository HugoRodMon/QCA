"""C.Gottmann: pdf with one grid per species, prices under the size headings.

    MANGOS                                                                          <- section
    Product Origin Brand      Weight ETA  Class Pack Box p.p x5  x6   x7  ... mix   <- header with sizes
    Keitt   BRA    Finofruits 4,0 KG      I     CRT  252         4,75     5,00      <- prices under the sizes
    WATERMELONS - PRICES PER KG                                                     <- prices per kg
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._pdf import nearest

PACKS = {"CRT": "CARTON", "PLS": "PLASTIC", "BAG": "BAGS"}


@register
class Gottmann(Supplier):
    name = "C.Gottmann"
    final_file = "C.Gottmann.xlsx"
    match_names = ["gottmann"]
    match_text = ["gottmann"]
    layout_hints = [r"product origin brand weight eta class pack box p\.?p"]
    layout = "wide"
    origin_style = "name"
    default_packaging = "CARTON"
    default_cat = 1

    def parse(self, doc):
        rows, section, x, sizes = [], "", None, []
        for line in doc.lines:
            texts = [w.text for w in line.words]
            if texts[:1] == ["Product"] and "Origin" in texts:
                pos = {w.text: w.x0 for w in line.words}
                x = {"origin": pos["Origin"] - 3, "brand": pos["Brand"] - 8, "weight": pos["Weight"] - 5,
                     "eta": pos["ETA"] - 9, "class": pos["Class"] - 3, "pack": pos["Pack"] - 3,
                     "pp": pos["Box"] - 4}
                grid = [w for w in line.words if w.x0 > pos["Box"] + 20]
                sizes = [(size_label(w.text), w.x0) for w in grid if w.text.lower() not in ("short", "long")]
                x["grid"] = min((sx for _, sx in sizes), default=10_000) - 10
                continue
            if line.size > line.words[0].size and line.text.isupper() or (line.text.isupper() and len(line.words) <= 6
                                                                         and not any(c.isdigit() for c in line.text)):
                section = line.text
                continue
            if x is None or not any(x["origin"] <= w.x0 < x["brand"] for w in line.words):
                continue
            rows += self.product_rows(line, x, sizes, section)
        return rows

    def product_rows(self, line, x, sizes, section):
        def part(a, b):
            return " ".join(w.text for w in line.words if x[a] <= w.x0 < x[b])

        product = " ".join(w.text for w in line.words if w.x0 < x["origin"])
        brand = part("brand", "weight")
        pack = N.pack_detail(brand)
        if pack:                                         # "12x 125 gr punnet" sits in the brand column
            brand = ""
        pp = re.match(r"\d+", part("pp", "grid"))
        per_kg = "PER KG" in section.upper()
        out = []
        for w in line.words:
            if w.x0 < x["grid"]:
                continue
            price = N.parse_plain_price(w.text) if re.fullmatch(r"\d+,\d{2}", w.text) else None
            if price is None:
                continue                                 # EXP / POR
            i = nearest(w.x0, [sx for _, sx in sizes], max_dist=14)
            if i is None:
                continue
            out.append(self.row(
                specie=f"{product} {section}", variety=product, origin=part("origin", "brand"), brand=brand,
                weight=N.parse_weight(part("weight", "eta")), cat=roman(part("class", "pack")),
                packaging=PACKS.get(part("pack", "pp").upper(), part("pack", "pp")),
                box_pp=int(pp[0]) if pp else None, size=sizes[i][0], price=price,
                not_final=getattr(w, "red", False),                          # printed in red: may not be final
                detail=" ".join(v for v in (pack, "Price/kg" if per_kg else "") if v)))
        return out


def size_label(t):
    """'x36' -> 36, 'mix' -> 'Mix', '12+' stays."""
    t = re.sub(r"(?i)^x(?=\d)", "", t)
    return "Mix" if t.lower() == "mix" else N.clean_size(t)


def roman(t):
    return {"I": 1, "II": 2, "III": 3}.get(t.strip().upper(), t.strip())

"""H&H (Hars & Hagebauer): 'Kiwi.. Daily Offer', a picture of small tables (read with OCR).

    KIWI GREECE                                                          <- section (not needed)
    Product           Origin   Size   Pallet   KG     Price              <- header (column places)
    Kiwi "HAYWARD"    Greece   20     80       10kg   € 17,00            <- variety in quotes, boxes per pallet
Each number is checked against a second OCR reading; a price the two don't agree on is marked red.
"""
import re

from .. import normalize as N
from ..base import Supplier, register

HEADER = ("product", "origin", "size", "pallet", "kg", "price")


@register
class HH(Supplier):
    name = "H&H"
    final_file = "H&H.xlsx"
    match_names = ["h&h", "hars", "hagebauer"]
    match_text = ["hagebauer", "kiwi specialist"]
    file_types = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf")
    origin_style = "name"

    def parse(self, doc):
        rows, x = [], None
        for line in doc.lines:
            words = [w.text.lower() for w in line.words]
            if "product" in words and "price" in words:
                x = {w.text.lower(): w.x0 for w in line.words if w.text.lower() in HEADER}
                continue
            if not x:
                continue
            c = self.cells(line, x)
            price = N.parse_plain_price(re.sub(r"[€\s]", "", c["price"]))
            if price is None or not c["product"]:
                continue
            product = c["product"]
            m = re.search(r"[\"“”']+\s*([^\"“”']+?)\s*[\"“”']+", product)
            variety = m[1].strip().title() if m else ""
            specie = re.sub(r"[\"“”'].*$", "", product).strip() or product
            row = self.row(specie=specie, variety=variety, origin=c["origin"],
                           size=N.clean_size(c["size"]) or "N/S", weight=N.parse_weight(c["kg"]),
                           box_pp=N.to_number(c["pallet"]) if c["pallet"].isdigit() else None, price=price)
            other = self.second_price(doc, line)
            if other is not None and abs(other - price) > 0.001:
                row.flag = f"read from a picture: the price looks like {price:g} or {other:g}"
            rows.append(row)
        return rows

    @staticmethod
    def cells(line, x):
        """The line's words by column: each word goes to the header it's nearest after (left-aligned product)."""
        order = sorted(x.items(), key=lambda kv: kv[1])
        out = {k: [] for k in HEADER}
        for w in line.words:
            name = order[0][0]
            for k, start in order:
                if w.x0 >= start - 40:                     # centred columns start a little left of their heading
                    name = k
            out[name].append(w.text)
        return {k: " ".join(v) for k, v in out.items()}

    @staticmethod
    def second_price(doc, line):
        """The same row's price in the second OCR reading (to catch a misread digit), or None."""
        for other in doc.second or []:
            if abs(other.top - line.top) < 12:
                prices = [N.parse_plain_price(w.text) for w in other.words if re.fullmatch(r"\d+[.,]\d{2}", w.text)]
                prices = [p for p in prices if p is not None]
                return prices[-1] if prices else None
        return None

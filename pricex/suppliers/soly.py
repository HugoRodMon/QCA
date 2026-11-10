"""SOLY: a short text file, a product heading followed by its sizes and prices; several products in one file.

    AVOCADO HASS MOROCCO
    SIZE 12/14 : 15.50€
    SIZE 22 : 9.50€
    SIZE 24 : 9.00€
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._common import box_material, clean, clean_size, describe


@register
class Soly(Supplier):
    name = "SOLY"
    final_file = "Soly Import.xlsx"
    match_names = ["soly"]
    layout_hints = [r"(?im)^size\s+[\d/&+ -]+\s*:\s*[\d.,]+\s*€\s*$"]
    file_types = (".txt",)
    origin_style = "name"
    default_brand = "Generic"     # as the final file writes it when no brand is given
    must_fill = ("WEIGHT (KG)",)  # their texts don't give the box weight: left empty, in red

    def parse(self, doc):
        rows, head = [], None
        for raw in doc.text.splitlines():
            line = clean(raw)
            if not line:
                continue
            price = N.parse_price(line)
            if price is None:                           # whole euros: '11€'
                m = re.search(r"(?<![\d.,])(\d+)\s*(?:€|eur\b)", line, re.I)
                price = float(m[1]) if m else None
            if price is None:
                head = describe(line)                   # a product: AVOCADO HASS MOROCCO
                continue
            if head is None:
                continue
            # 'SIZE 12/14 : 15.50€': the size is what comes before the colon (or before the price)
            size = line.split(":", 1)[0] if ":" in line else re.split(r"€|\d+[.,]\d{2}", line)[0]
            species = head["species"] or head["variety"]
            variety = head["variety"].title() if head["variety"].isupper() else head["variety"]     # HASS -> Hass
            rows.append(self.row(
                specie=species, variety=variety, origin=head["origin"],
                size=clean_size(size) or "N/S", weight=head["weight"], box_pp=head["box_pp"],
                packaging=box_material(head["species"], head["weight"]), price=price, detail=head["pack"] or ""))
        return rows

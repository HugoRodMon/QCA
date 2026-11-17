"""Fair Connection: an Excel sheet, a product line followed by its sizes and net prices.

    A                                                          B             C
    AVOCADOS                                                                              <- section (ignored)
    Avocado 10kg from Colombia (Hass)                                                     <- product
                                                               SIZE/ PACK    NET PRICE
                                                               14/ 16/ 18    30           <- one row per size
    Blueberry 12x125 carton from Peru (Abril/ Berry Princess)                             <- one row per variety
                                                               14mm+         €20,00
    Mandarins from Peru 10kg OT (Nadorcott/Tango)                                         <- DETAIL: OT Open Top, TC Telescopic
                                                               1X/ 1/ 2      € 16,00
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._common import box_material, clean, describe

PRODUCT_RE = re.compile(r"(?i)^(?P<what>.*?)\s+from\s+(?P<origin>.+?)\s*(?:\((?P<varieties>[^)]*)\))?\s*$")
BOX_WORDS = r"(?i)\b(?:OT|TC|open\s*top|telescopic|carton|ctn)\b"
BOX_DETAIL = [(r"(?i)\b(?:TC|telescopic)\b", "Telescopic"), (r"(?i)\b(?:OT|open\s*top)\b", "Open Top")]


@register
class FairConnection(Supplier):
    name = "Fair Connection"
    final_file = "FairConnection.xlsx"
    match_names = ["fair connection", "fairconnection"]
    match_text = ["fair connection", "fairconnection"]
    layout_hints = [r"size/ ?pack\s+net price"]
    file_types = (".xlsx",)
    origin_style = "name"
    default_cat = "I"

    def parse(self, doc):
        rows = []
        for sheet in doc.sheets.values():
            product = None
            for cells in sheet:
                a, b, c = (list(cells) + [None, None, None])[:3]
                if a not in (None, "") and b in (None, "") and c in (None, ""):
                    product = self.read_product(str(a))          # None for a section like 'AVOCADOS'
                    continue
                if product is None or b in (None, "") or str(b).strip().upper().startswith("SIZE"):
                    continue
                price = N.parse_price(c) if not isinstance(c, (int, float)) else float(c)
                if price is None:
                    price = N.parse_plain_price(c)
                if price is None:
                    continue
                for size in self.sizes(b):
                    for variety in product["varieties"]:
                        rows.append(self.row(
                            specie=product["species"], variety=variety, origin=product["origin"], size=size,
                            weight=product["weight"], packaging=box_material(product["species"], product["weight"]),
                            price=price, detail=product["detail"]))
        return rows

    def finalize(self, rows, result):
        out = super().finalize(rows, result)
        for r in out:                         # their final file writes 'Carton 10x500g', not 'CARTON 10X500G'
            r.packaging = re.sub(r"(?i)^carton(\s+\d+)x(\d+)g$", r"Carton\1x\2g", r.packaging or "")
        return out

    @staticmethod
    def read_product(text):
        m = PRODUCT_RE.match(clean(text))
        if not m:
            return None
        rest = m["origin"]                    # 'Peru 10kg OT' / 'South Africa 15kg TC'
        what = f"{m['what']} {rest}"
        head = describe(re.sub(BOX_WORDS, " ", what))
        origin = describe(rest)["origin"] or re.sub(r"(?i)\d.*$", "", rest).strip()
        varieties = [v.strip() for v in (m["varieties"] or "").split("/") if v.strip()] or [head["variety"]]
        detail = next((name for rx, name in BOX_DETAIL if re.search(rx, what)), "")
        return {"species": head["species"] or m["what"], "origin": origin, "weight": head["weight"],
                "varieties": varieties, "detail": detail}

    @staticmethod
    def sizes(value):
        """'14/ 16/ 18' -> [14, 16, 18], 'XXL/ J' -> ['XXL', 'J'], '14mm+' -> ['14+'], 72 -> [72]."""
        if isinstance(value, (int, float)):
            return [N.to_number(value)]
        out = []
        for s in str(value).replace("\xa0", " ").split("/"):
            s = re.sub(r"(?i)\s*mm", "", s.strip())
            if s:
                out.append(int(s) if s.isdigit() else s.upper())
        return out

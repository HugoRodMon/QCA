"""Schrijvershof: their 'Fresh Updates' web page saved from the browser (.mhtml), in Dutch.

    <h2>Mango - Brazilië</h2>                                                   <- species - origin
    Variëteit | Maat | Merk | Kl. | Gewicht | Verpakking | ETA | Prijs EUR     <- header
    Keitt     | 6 st | Pingo de Mel | 1 | 4 kg |  | 30-11-2026 | 5,50          <- one row per size
A row without a price (sold out, on request) is left out.
"""
import re

from bs4 import BeautifulSoup

from .. import normalize as N
from ..base import Supplier, register

COLUMNS = {"variëteit": "variety", "varieteit": "variety", "maat": "size", "merk": "brand", "kl.": "cat", "kl": "cat",
           "gewicht": "weight", "verpakking": "packing", "eta": "eta", "prijs": "price", "prijs eur": "price"}


@register
class Schrijvershof(Supplier):
    name = "SCHRIJVERSHOF"
    final_file = "SCHRIJVERSHOF.xlsx"
    match_names = ["schrijvershof"]
    match_text = ["schrijvershof"]
    file_types = (".mhtml", ".mht", ".html", ".htm")
    origin_style = "name"

    def parse(self, doc):
        soup = BeautifulSoup(doc.html, "html.parser")
        rows, species, origin, columns = [], "", "", []
        for el in soup.find_all(lambda t: t.name == "h2" or (t.name == "div" and t.get("class")
                                                               and {"product_row_head", "product_row"} & set(t["class"]))):
            if el.name == "h2":                                     # 'Mango - Brazilië'
                species, _, origin = (x.strip() for x in el.get_text(" ", strip=True).partition(" - "))
                columns = []
                continue
            cells = [c.get_text(" ", strip=True) for c in el.select(".c")]
            if "product_row_head" in el["class"]:
                columns = [COLUMNS.get(c.lower(), c.lower()) for c in cells]
                continue
            if not columns or not species:
                continue
            v = dict(zip(columns, cells))
            price = N.parse_plain_price(v.get("price"))
            if price is None:
                continue
            size = re.sub(r"(?i)\s*st\.?$", "", v.get("size", "")).strip()       # '6 st' -> 6
            cat = v.get("cat", "")
            rows.append(self.row(
                specie=species, variety=v.get("variety", ""), origin=origin, size=N.clean_size(size) or "N/S",
                weight=N.parse_weight(v.get("weight")), brand=v.get("brand", ""),
                cat=int(cat) if cat.isdigit() else cat, price=price,
                packaging=N.packaging_from(v.get("packing", "")) or "", detail=v.get("packing", "")))
        return rows

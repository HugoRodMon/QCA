"""Verdi: Excel price list (Dutch).

    Sinaasappelen TC                                         <- section (species, box type)
    Product | Origin | Merk | Gewicht | P/P | Prijzen in Euro
    Delta Seedless | ZA | Cochari | 15kg | 80 | 40 | 48 | 56 | Cat 2     <- product row with sizes
                                            | 14 | 14 | 13               <- prices under the sizes
                                            | 26-10 | 26-10            <- arrival dates (ignored)
             | Cochari | 15kg | 80 | 64 | 72                            <- same product, other brand/class
"""
import re
from datetime import datetime

from .. import normalize as N
from ..base import Supplier, register

FIRST_SIZE_COL = 5          # column F


@register
class Verdi(Supplier):
    name = "Verdi"
    final_file = "Verdi.xlsx"
    match_names = ["verdi"]
    match_text = ["0031 (0)180 61 88 11"]
    layout_hints = [r"prijzen in euro", r"product\s+merk\s+gewicht\s+p/p"]
    file_types = (".xlsx", ".xlsm")
    layout = "wide"
    origin_style = "source"

    def parse(self, doc):
        rows = []
        if not any(str(r[0]).strip().lower() == "product" and "merk" in [str(v).strip().lower() for v in r]
                   for t in doc.sheets.values() for r in t if r):
            raise ValueError("no 'Product | Origin | Merk | Gewicht' header found")
        for table in doc.sheets.values():
            section, product, origin = "", "", ""
            i = 0
            while i < len(table):
                r = (table[i] + [None] * 20)[:20]
                a = text(r[0])
                if a and not any(text(v) for v in r[1:]):          # section title
                    section, product, origin = a, "", ""
                    i += 1
                    continue
                if a.lower() == "product":
                    i += 1
                    continue
                is_product_row = text(r[3]) and text(r[4]) and any(text(v) for v in r[FIRST_SIZE_COL:])
                if not is_product_row or i + 1 >= len(table):
                    i += 1
                    continue
                if a:
                    product, origin = a, text(r[1])
                prices = (table[i + 1] + [None] * 20)[:20]
                if not N.is_ignored(section):     # a whole section we don't track ('Tomaten': 'Cherry Tros' too)
                    rows += self.product_rows(section, product, origin, r, prices)
                i += 2
        return rows

    def product_rows(self, section, product, origin, r, prices):
        brand, weight_txt, pp = text(r[2]), text(r[3]), text(r[4])
        weight = N.parse_weight(weight_txt)
        pack = N.pack_detail(weight_txt) or ""
        detail = N.box_type(section)
        cat = ""
        extras = []
        sizes = []
        for col in range(FIRST_SIZE_COL, len(r)):
            head = r[col]
            if head is None or text(head) == "":
                continue
            price = N.parse_plain_price(prices[col]) if not isinstance(prices[col], datetime) else None
            if price is None:
                h = text(head)
                if re.fullmatch(r"(?i)cat\.?\s*(2|ii)", h):
                    cat = 2
                elif h:
                    extras.append(h)
                continue
            sizes.append((head, price))

        out = []
        for head, price in sizes:
            size, size_detail = split_head(head)
            if N.pack_detail(size):
                size_detail = size_detail or N.pack_detail(size)
                size = "N/S"
            out.append(self.row(
                specie=product if N.find_species(product) else f"{product} {section}",
                variety=variety(product, section),
                origin=origin.strip(), size=size, weight=weight, brand=brand,
                box_pp=N.to_number(pp), cat=cat, price=price,
                detail=" ".join(x for x in (pack, detail or size_detail) if x)))
        return out


def text(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d-%m")
    return str(v).replace(" ", " ").strip()


def split_head(head):
    """'45-OT' -> (45, 'Open Top'), 'L-Basket' -> ('L', ''), '1XX-60' -> ('1XX', ''),
    1982-01-01 (Excel turned '1-82' into a date) -> ('1-82', '')."""
    if isinstance(head, datetime):
        return f"{head.month}-{head.year % 100}", ""
    h = text(head)
    m = re.fullmatch(r"(?i)([\w+/]+?)-(ot|tc|basket|label|layered|los)", h)
    if m:
        return N.clean_size(m[1]), N.box_type(m[2])
    m = re.fullmatch(r"(?i)(1?X{1,3}|\d)-\d+", h)                # 1XX-60 (size code - count)
    if m:
        return m[1], ""
    m = re.fullmatch(r"(?i)(\d+(?:[.,]\d+)?)\s*kg", h)          # weight written as the size
    if m:
        return "N/S", ""
    return N.clean_size(h), ""


def variety(product, section):
    """Product name without the species word: 'Avocado Bacon' -> 'Bacon', 'Kiwi Hayward' -> 'Hayward'."""
    species = N.find_species(product)
    if not species:
        return product
    from ._common import remove_alias
    return remove_alias(product, species) or ""

"""EDN (El Dorado Netherlands): pdf table, product names in Dutch / English.

    Bellevue sweet potatoes                          Maat     Verpakking     P/P  Prijs       <- section + header
    Zoete aardappels / Sweet potatoes          EG    Large 1  6kg doos/box   180  € 4.00
    Bio Zoete aard / Organic Sweet pots        EG    Medium   6kg doos/box   160  € 7.50
    Knoflook normaal wit / Garlic normal white CN    50+      20x500gr       108  € 25.00
    Sinasappels / Oranges Valencia             RSA   C56      15 kg ds/box   80   € 15.65
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._common import remove_alias

SIZES = {"small": "S", "medium": "M", "large": "L", "large 1": "L1", "large 2": "L2", "xlarge": "XL",
         "extra large": "XL"}


@register
class EDN(Supplier):
    name = "EDN"
    final_file = "EDN.xlsx"
    match_names = ["edn"]
    match_text = ["ednbv", "el dorado netherlands"]
    layout_hints = [r"maat\s+verpakking\s+p/p\s+prijs"]
    origin_style = "source"
    default_cat = 1

    def parse(self, doc):
        rows, x = [], None
        for line in doc.lines:
            texts = [w.text for w in line.words]
            if "Maat" in texts and "Prijs" in texts:
                pos = {w.text: w.x0 for w in line.words}
                x = {"origin": pos["Maat"] - 35, "size": pos["Maat"] - 3, "pack": pos["Verpakking"] - 3,
                     "pp": pos["P/P"] - 3, "price": pos["Prijs"] - 15, "remark": pos["Prijs"] + 32}
                continue
            if x is None:
                continue
            rows.append(self.make_row(line, x))
        return [r for r in rows if r]

    def make_row(self, line, x):
        def part(a, b):
            return " ".join(w.text for w in line.words if x[a] <= w.x0 < (x[b] if b else 10_000))

        # some of their PDFs use a font Python can't read the € and spaces of: they come out as '(cid:934)(cid:3)',
        # and the price as '4 ,25'. The column says it's euros, so drop the codes and join the number.
        price_txt = re.sub(r"\(cid:\d+\)", " ", part("price", "remark"))
        price_txt = re.sub(r"(\d)\s+(?=[.,]\d)", r"\1", price_txt)
        price = N.parse_price(price_txt) or N.parse_plain_price(price_txt)
        if price is None:
            return None                                    # "-": no price today, or a section line
        name = " ".join(w.text for w in line.words if w.x0 < x["origin"])
        english = name.rsplit("/", 1)[1].strip() if "/" in name else name    # Dutch / English
        if re.match(r"(?i)organic\b", english) is None and re.match(r"(?i)(bio\b|bio/organic)", name):
            english = "Organic " + english
        species = N.find_species(english) or N.find_species(name)
        variety = remove_alias(english, species) if species else english
        variety = variety.title() if variety.islower() else variety          # normal white -> Normal White
        size_txt = part("size", "pack")
        detail = ""
        if size_txt.lower() == "peeled":                   # garlic: 'Peeled' sits in the size column
            detail, size_txt = "Peeled", ""
        size = SIZES.get(size_txt.lower(), re.sub(r"(?i)^c(?=\d)", "", size_txt))   # C56 -> 56
        packing = part("pack", "pp")
        pack = N.pack_detail(packing)
        return self.row(
            specie=species or english, variety=variety, origin=part("origin", "size"),
            size=size or "N/S", weight=N.parse_weight(re.sub(r"(?i)\s*(doos|ds)\s*/?\s*box", "", packing)),
            box_pp=N.to_number(part("pp", "price")), price=price,
            packaging="Carton" if re.search(r"(?i)box", packing) or pack else "",
            detail=" ".join(v for v in (detail, pack) if v))

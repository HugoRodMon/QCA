"""Kissao: pdf table. Prices are often printed on their own line just above the product row.

    Product        Origin Variety Size      Packing Boxes / pallet Price Availability
                                                                   € 9,50          <- price line
    Pomelos white  China  Honey   8/9/10/11 10kg    75                             <- its product
    Lime           Brazil Tahiti  42        4,5Kg   240            P.O.R ETA 28/10
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._common import remove_alias
from ._pdf import Columns, is_header
from ..ocr import closest, known

HEADER = ["Product", "Origin", "Variety", "Size", "Packing", "Boxes / pallet", "Price", "Availability"]
HEADER_WORDS = {"product", "origin", "variety", "size", "packing", "boxes", "pallet", "price", "availability", "plts"}
# species that always come with a size in this list (a missing size there means OCR lost it)
SIZED = {"Limes", "Mangoes", "Avocados", "Pomelos", "Pomegranates", "Sweet Potatoes", "Coconuts"}


def picture_columns(lines):
    """Column start positions from every header row of the picture (median of what OCR found)."""
    from statistics import median
    seen = {}
    for line in lines:
        words = [w for w in line.words if w.text.lower().strip("/") in HEADER_WORDS]
        if len(words) < 3:
            continue
        for w in words:
            seen.setdefault(w.text.lower().strip("/"), []).append(w.x0)
    if not {"variety", "size", "price"} <= set(seen):
        return None
    x = {k: median(v) for k, v in seen.items()}
    starts = [("Product", 0), ("Origin", x.get("origin", (x["variety"]) * 0.66) - 5),
              ("Variety", x["variety"] - 5),
              ("Size", (x["variety"] + 2 * x["size"]) / 3),           # sizes are centred: start well left
              ("Packing", x.get("packing", x["size"] + 45) - 5),
              ("Boxes / pallet", x.get("boxes", x["price"] - 75) - 5),
              ("Price", x["price"] - 15),                             # '€' sits left of the heading
              ("Availability", x.get("availability", x["price"] + 55) - 5)]
    cols = Columns([])
    cols.starts = starts
    return cols


def picture_origin(text):
    """'Braril' -> Brazil, 'Vietrans' -> Vietnam, 'CH/COL/GUA' kept; '' if it isn't a country."""
    t = text.strip(" .,'")
    if not t:
        return ""
    if N.is_origin(t) or ("/" in t and all(N.is_origin(p) for p in re.split(r"\s*/\s*", t))):
        return t
    countries = [c for c in N._origins()[0] if len(c) >= 4]
    match = closest(t.lower(), countries, 0.6)
    return match.title() if match else ""


def same_row(line, other_lines):
    """The row of the second reading at the same height (an empty row if there's none)."""
    from ..readers import Line
    mid = line.top + line.size / 2
    best = min(other_lines, key=lambda o: abs(o.top + o.size / 2 - mid), default=None)
    if best is None or abs(best.top + best.size / 2 - mid) > max(5, 0.6 * line.size):
        return Line([])
    return best


def _price(text):
    m = re.search(r"(\d+)[.,](\d{2})(?!\d)", text or "")
    return (float(f"{m[1]}.{m[2]}"), m[1]) if m else (None, None)


def picture_price(main_text, other_text, problems):
    """Prices: the second reading (Windows) reads numbers best. RapidOCR sometimes reads the '€' as a
    6 ('€ 6,00' -> '66,00'): that's not a disagreement."""
    main, main_int = _price(main_text)
    other, other_int = _price(other_text)
    if other is not None:
        if main is not None and main != other and not (main_int.endswith(other_int) and len(main_int) == len(other_int) + 1):
            problems.append(f"price read as €{main:g} and €{other:g}, used €{other:g}")
        return other
    if main is not None and len(main_int) >= 2 and main_int[0] in "6€" and main >= 60:
        problems.append(f"price €{main:g} may be €{float(main_int[1:] + '.' + f'{main:.2f}'[-2:]):g} ('€' read as 6)")
    return main


def valid_size(s):
    """A size that makes sense: 42, 250+, L1, M, 6-12, 10--24, 8/9/10 (going up)."""
    s = s.replace(" ", "")
    if re.fullmatch(r"\d+\+?|[SMLXJ]{1,3}\d?", s, re.I):
        return True
    parts = re.split(r"/|-{1,2}", s)
    if len(parts) > 1 and all(p.isdigit() for p in parts):
        nums = [int(p) for p in parts]
        return nums == sorted(set(nums)) and max(nums) <= 3 * min(nums) + 10
    return bool(re.fullmatch(r"([SMLX]{1,2}\d?/)+[SMLX]{1,2}\d?", s, re.I))


def picture_check(main, other, what, problems, is_valid):
    """Compare the two readings of a cell: if they disagree, keep the one that makes sense and note it."""
    a, b = (main or "").strip(), (other or "").strip()
    same = lambda x, y: re.sub(r"[\s-]", "", x.lower()) == re.sub(r"[\s-]", "", y.lower())  # noqa: E731
    if not b or not a or same(a, b):
        if a and not is_valid(a):
            problems.append(f"{what} '{a}' unclear")
        elif what == "variety" and a and not b:
            # only one reading saw it (e.g. Keitt vs Kent can't be double-checked)
            problems.append(f"variety '{a}' read only once")
        return a or b
    pick = a if is_valid(a) or not is_valid(b) else b
    problems.append(f"{what} read as '{a}' and '{b}', used '{pick}'")
    return pick


def picture_size(text):
    """Fix what OCR does to sizes: 'to..24' -> 10--24, '2508 €' -> 250+, 'LI' -> L1, '79/10/11' kept."""
    s = text.replace("€", "").strip()
    m = re.fullmatch(r"(\d{3})[g8]\s*[+\-~]?", s)              # 250g+, 2508 (g read as 8), 250g-
    if m:
        return m[1] + "+"
    if re.search(r"\d", s):
        fixed = s.translate(str.maketrans({"o": "0", "O": "0", "t": "1", "l": "1", "I": "1", "s": "5", "S": "5"}))
        fixed = fixed.replace("..", "--").replace("—", "--")
        if re.fullmatch(r"[\d/+\-]+", fixed):
            return fixed
    m = re.fullmatch(r"([LMSX]{1,2})[Il|]", s)
    if m:
        return m[1] + "1"
    return s


@register
class Kissao(Supplier):
    name = "Kissao"
    final_file = "Kissao.xlsx"
    match_names = ["kissao"]
    match_text = ["kissao", "kinobe", "kinobé"]
    file_types = (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
    layout_hints = [r"boxes\s*/\s*pallet", r"daily export offer"]
    origin_style = "name"
    species_names = {"Passion Fruits": "Passion fruit", "Sweet Potatoes": "Sweet potato",
                     "Granadillas": "Granadilla", "Tamarinds": "Tamarind", "Mangosteens": "Mangosteen",
                     "Guavas": "Guava", "Dragon Fruits": "Pithaya"}

    def parse(self, doc):
        if doc.kind == "image":
            return self.parse_picture(doc)
        rows, cols, pending = [], None, None
        for line in doc.lines:
            if is_header(line, "product", "origin", "price"):
                cols = Columns.from_header(line, HEADER)
                pending = None
                continue
            if cols is None:
                continue
            c = cols.split(line)
            price_text = f'{c["Boxes / pallet"]} {c["Price"]}'     # the € sign can sit left of the column
            if not c["Product"] and c["Price"]:               # price printed above its row
                pending = N.parse_price(price_text)
                continue
            if not (c["Product"] and c["Origin"]):
                continue
            price = N.parse_price(price_text)
            if price is None and pending is not None and not re.search(r"(?i)p\.?o\.?r", c["Price"]):
                price = pending
            pending = None
            if price is None:
                continue
            rows.append(self.make_row(c, price))
        return rows

    # ------------------------------------------------------------ price list sent as a picture
    def parse_picture(self, doc):
        """Same table read with OCR. Column positions come from all the header rows together (OCR drops
        words here and there); prices are the numbers in the Price column ('€' is often misread);
        rows with something missing are kept but marked for checking."""
        cols = picture_columns(doc.lines)
        if cols is None:
            raise ValueError("no 'Product / Origin / Variety / Size / Price' header found in the picture")
        rows = []
        for line in doc.lines:
            if sum(w.text.lower().strip("/") in HEADER_WORDS for w in line.words) >= 3:
                continue                                              # a header row
            c = cols.split(line)
            if not c["Product"] or re.fullmatch(r"[A-Z ]+", c["Product"]) and len(line.words) <= 2:
                continue                                              # empty or a section title
            other = cols.split(same_row(line, doc.second)) if doc.second else {}
            problems = []
            price = picture_price(c["Price"], re.sub(r"(\d)\s+(\d{2})\b", r"\1,\2", other.get("Price", "")),
                                  problems)                           # Windows may read '9,50' as '9 50'
            if price is None:
                continue                                              # P.O.R / empty
            c["Size"] = picture_check(picture_size(c["Size"]),
                                      picture_size(other.get("Size", "").split(" ")[0]), "size", problems, valid_size)
            c["Variety"] = picture_check(c["Variety"], other.get("Variety", ""), "variety", problems, known)
            c["Origin"] = picture_origin(c["Origin"]) or picture_origin(other.get("Origin", ""))
            row = self.make_row(c, price)
            species = N.find_species(row.specie) or N.species_from_variety(row.variety) \
                or N.find_species(row.specie.replace("potato", " potato"))
            missing = [name for name, v in (("origin", row.origin), ("boxes/pallet", row.box_pp)) if not v]
            if not c["Size"] and species in SIZED:
                missing.append("size")
            odd = [s for s in re.split(r"[/-]+", c["Size"]) if s.isdigit() and int(s) > 400]   # e.g. '677'
            if odd:
                problems.append(f"size {c['Size']} doesn't exist for {species}")
            if missing:
                problems.append("missing " + ", ".join(missing))
            if problems:
                row.flag = "read from a picture: " + "; ".join(problems)
            rows.append(row)
        return rows

    def make_row(self, c, price):
        product, variety, type_, brand = c["Product"], c["Variety"], "", ""
        # long size groups start left of the Size column, after a variety or alone ('14/15/18/20')
        m = re.search(r"(?:^|\s+)(\d+(?:\s*[/-]+\s*\d+)+)$", variety)
        if m:
            c["Size"] = (m[1] + " " + c["Size"]).strip()
            variety = variety[:m.start()]
        for text in (product, variety):
            m = re.search(r"(?i)\bby (air|boat|sea)\b", text)
            if m:
                type_ = m[0].upper()
        product = re.sub(r"(?i)\bby (air|boat|sea)\b", "", product).strip()
        variety = re.sub(r"(?i)\bby (air|boat|sea)\b", "", variety).strip()
        if re.search(r"(?i)mrl free", product):
            brand = "MRL Free"
            product = re.sub(r"(?i)mrl free", "", product).strip()
        species = N.find_species(product)
        if not variety and species:
            rest = remove_alias(re.sub(r"(?i)young coco", "", product), species).strip()
            variety = rest.title() if rest and rest.lower() not in ("white", "red") else ""
        packing = c["Packing"]
        size = re.sub(r"(?i)(\d+)\s*g?\s*\+", r"\1+", c["Size"]).strip()
        pack = N.pack_detail(packing)
        return self.row(
            specie=product, variety=variety, origin=c["Origin"], size=size or "N/S",
            weight=N.parse_weight(packing), packaging=N.packaging_from(packing),
            box_pp=N.to_number(c["Boxes / pallet"]), price=price, brand=brand, type=type_,
            detail=pack or "")

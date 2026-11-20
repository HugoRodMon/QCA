"""Atlantic Fruit: a short WhatsApp text. A product heading, lines with pallets / sizes / pack, then the price
for the lines above it (or the price on the same line).

    In Stock (NL)
    Passion Fruit Colombia                                   <- species + origin
    x1p 32-36s                                               <- 1 pallet, sizes 32-36
    x3p 40-44s
    9,50 EUR/box                                             <- the price for every line above it
    Drink Coconuts Vietnam
    7xp (9pc, Easy Open)                                     <- 7 pallets, size 9 (pieces), DETAIL Easy Open
    Brown Coconuts Ivory Coast (21kg. bags)                  <- 21 kg, packaging Bags
    Blueberries Peru
    Eureka Bulk 3,5kg. +14mm 12,85 EUR/kg.                   <- variety, size 14+, price per kg
    Figs Black Mission PERU
    12x160g  P.O.R  22,00 EUR/box                            <- pack 12x160g (1.92 kg)
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._common import clean, describe

PRICE_RE = re.compile(r"(?i)(\d+(?:[.,]\d+)?)\s*(?:€|eur)\b\.?\s*(?:/\s*(box|kg|ctn|carton|bag)\b)?")
PALLETS_RE = re.compile(r"(?i)(?<![\w.,])x?\s*(\d+(?:[.,]\d+)?)\s*x?\s*p\b(?!\.?o)")
SIZE_RE = re.compile(r"(?i)(?<![\w.,])(\d+(?:\s*[-/]\s*\d+)*)\s*s\b|\+\s*(\d+)\s*mm\b|(\d+)\s*mm\s*\+|\(?(\d+)\s*pc")
WORDS = [(r"(?i)\bloose\b", "Loose"), (r"(?i)\bbulk\b", "Bulk"), (r"(?i)\beasy\s*open\b", "Easy Open")]
SKIP = r"(?i)^(?:sure|here you go|in stock|atlantic fruit)\b"
NOT_VARIETY = r"(?i)\bp\.?o\.?r\.?\b|\bbox(?:es)?\b|\bkg\b|\bpc\b|[(),.+]"


@register
class AtlanticFruit(Supplier):
    name = "Atlantic Fruit"
    final_file = "Atlantic Fruit.xlsx"
    match_names = ["atlantic fruit", "atlanticfruit", "atlantic"]
    match_text = ["atlantic fruit"]
    file_types = (".txt",)
    origin_style = "name"
    must_fill = ("WEIGHT (KG)",)  # when the message doesn't say the box weight: left empty, in red

    def parse(self, doc):
        rows, head, waiting = [], None, []
        for raw in doc.text.splitlines():
            line = clean(raw)
            if not line or re.search(SKIP, line):
                continue
            m = PRICE_RE.search(line)
            before = line[:m.start()] if m else line
            if not m and describe(line)["species"]:
                head, waiting = self.read_heading(line), []
                continue
            if head is None:
                continue
            if not m:
                waiting.append(self.read_item(before))          # 'x1p 32-36s': price comes later
                continue
            price = N.to_number(m[1].replace(",", "."))
            per_kg = (m[2] or "").lower() == "kg"
            items = waiting if not before.strip() and waiting else [self.read_item(before)]
            waiting = []
            for it in items:
                weight = it["weight"] or head["weight"]
                detail = " ".join(x for x in (it["pack"], *it["words"], *head["words"], "Price/kg" if per_kg else "") if x)
                for size in it["sizes"] or ["N/S"]:
                    rows.append(self.row(
                        specie=head["species"], variety=it["variety"] or head["variety"], origin=head["origin"],
                        size=size, weight=weight, packaging=head["packaging"], price=price, detail=detail))
        return rows

    @staticmethod
    def read_heading(line):
        """'Brown Coconuts Ivory Coast (21kg. bags)' -> species, variety, origin, weight, packaging."""
        packaging = "Bags" if re.search(r"(?i)\bbags?\b", line) else ""
        t = re.sub(r"(?i)\bbags?\b", " ", line)
        words = [name for rx, name in WORDS if re.search(rx, t)]
        for rx, _ in WORDS:
            t = re.sub(rx, " ", t)
        origin = ""
        lookup, _ = N._origins()
        for name in sorted((k for k in lookup if " " in k), key=len, reverse=True):   # 'Ivory Coast', 'South Africa'
            m = re.search(rf"(?i)(?<!\w){re.escape(name)}(?!\w)", t)
            if m:
                origin, t = lookup[name], t[:m.start()] + " " + t[m.end():]
                break
        head = describe(t)
        head["origin"] = head["origin"] or origin
        variety = re.sub(r"\s+", " ", re.sub(NOT_VARIETY, " ", head["variety"])).strip(" -")
        variety = variety.title() if variety.isupper() or variety.islower() else variety
        return {"species": head["species"], "variety": variety, "origin": head["origin"],
                "weight": head["weight"], "packaging": packaging, "words": words}

    @staticmethod
    def read_item(text):
        """'x1p 32-36s', '7xp (9pc, Easy Open)', 'Eureka Bulk 3,5kg. +14mm', '12x160g P.O.R'."""
        t = text
        words = [name for rx, name in WORDS if re.search(rx, t)]
        for rx, _ in WORDS:
            t = re.sub(rx, " ", t)
        pack = N.pack_detail(t) if re.search(r"(?i)\d+\s*x\s*\d+\s*(?:g|gr|kg)\b", t) else ""
        weight = N.find_weight(t)
        t = re.sub(r"(?i)\d+\s*x\s*\d+(?:[.,]\d+)?\s*(?:kg|gr?|gram)\b|(?<![\w.,])\d+(?:[.,]\d+)?\s*kg\b\.?", " ", t)
        sizes = []
        for m in SIZE_RE.finditer(t):
            if m[1]:
                sizes.append(re.sub(r"\s+", "", m[1]))
            elif m[2] or m[3]:
                sizes.append(f"{m[2] or m[3]}+")              # '+14mm' -> 14+
            elif m[4]:
                sizes.append(int(m[4]))                       # '(9pc' -> 9 pieces a box
        t = SIZE_RE.sub(" ", t)
        p = PALLETS_RE.search(t)
        if p:
            words.insert(0, f"{p[1].replace(',', '.')}P")     # 'x3p' -> 3P
            t = t[:p.start()] + " " + t[p.end():]
        t = re.sub(r"(?i)\b\d+(?:[.,]\d+)?\s*g\b\.?", " ", t)   # '2,4g.': a weight we can't trust
        variety = re.sub(r"\s+", " ", re.sub(NOT_VARIETY, " ", t)).strip(" -x")
        variety = "" if re.fullmatch(r"[\d\s]*", variety) else variety
        return {"sizes": [int(s) if str(s).isdigit() else s for s in sizes], "weight": weight, "pack": pack or "",
                "words": words, "variety": variety.title() if variety.isupper() or variety.islower() else variety}

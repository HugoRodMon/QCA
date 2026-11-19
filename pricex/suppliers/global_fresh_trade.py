"""Global Fresh Trade: a German/English WhatsApp-style text. A product line, with its price or followed by
lines of sizes and prices (several on one line).

    Good Morning   Guten morgen  18-11-2026           our pricelist           unsere Angebote
    *** special today   Ginger China 12 kg 90 pp   white boxes     EURO 17.75    <- product and price
    Commice pears 12 kg  65 +  cat 1                                             <- no price: not kept
    Valencia                                                                     <- variety for the next lines
    Oranges 72   Zim  € 10.75                                                    <- size 72, Zimbabwe
    Oranges  Valencia cat 1 105      € 8.75            by lorry   € 8.50         <- 2nd price: DETAIL By lorry
    Lemons 15 kg  Egt  80 pp                                                     <- product...
      88 € 17.50             100 € 18.50         113  € 18.00                    <- ...sizes and prices
    Granatäpfel Pomegrate  10 kg  cat 1 Marokko   100 pp
    Grösse/Kal. 18  € 12.50                 Grösse/Kal. 20  €11.50               <- Grösse/Kal., Cal. = size
    Limes by air Brasil 54/60   st € 16.50  dark green !!                        <- TYPE BY AIR, sizes 54, 60
    Bananen 18 kg  54 pp    Fyffes  € 15.00                                      <- brand
"""
import json
import re

from .. import normalize as N
from ..base import Supplier, register
from ._common import box_material, clean, describe

PRICE_RE = re.compile(r"(?i)(?:€|\beuro?\b)\s*(\d+(?:[.,]\d+)?)")
CAT_RE = re.compile(r"(?i)\bcat\.?\s*(I{1,2}|\d)\b")
SIZE_RE = re.compile(r"(?i)(?:gr(?:ö|oe|o)sse\s*/\s*)?(?:\bcal|\bkal)\.?\s*(\d+)|(?<![\w.,])(\d+(?:\s*/\s*\d+)*\s*\+?)(?:\s*st\b)?")
# words that are not the variety: German names, greetings, our own notes
NOISE = (r"(?i)\*+|\bspecial today\b|\bfresh\b|\bdrink\b|\btrauben\b|\bmais\b|\bblatt\b|\bvakuum\b|\bgekochte\b|"
         r"\bgr(?:ö|oe|o)sse\b|!+")
DETAILS = [(r"(?i)\bwhite box(?:es)?\b", "White boxes"), (r"(?i)\bpurple box(?:es)?\b", "Purple box"),
           (r"(?i)\beasy(?: open)?\b", "Easy open"), (r"(?i)\bleaf\b", "Leaf")]
DROP = r"(?i)\bdark green\b"                 # a remark on the fruit, not kept
BRANDS = ("fyffes", "chiquita", "dole", "del monte", "bonita")


VARIETY_WORDS = ("clementine",)       # names of the species that are also the variety we type
# 'Mandarins Berkane Top': a Moroccan clementine sold under that name -> (variety, origin), name as BRAND
NAMED = {r"berkane(?:\s+top)?": ("Clementine", "Morocco")}
# box weight when the list doesn't say it: filled in, but red so it gets checked
DEFAULT_WEIGHT = {"Oranges": 4, "Mandarins": 4, "Limes": 4}


def has_words(text):
    """True when the text has words besides sizes ('Fresh Corn Mais Marocco 30 st'), not '100' or 'cal. 2'."""
    t = re.sub(r"(?i)\b(?:by lorry|lkw)\b|gr(?:ö|oe|o)sse|\b(?:cal|kal|st)\b|\d+(?:[.,]\d+)?\s*(?:x\s*\d+(?:[.,]\d+)?)?\s*(?:kg|gr?)?",
               " ", text)
    return bool(re.search(r"[^\W\d_]{3,}", t))


def _aliases(species):
    data = json.loads((N.DATA / "species.json").read_text(encoding="utf-8"))
    return sorted([species] + data["species"].get(species, []), key=len, reverse=True)


@register
class GlobalFreshTrade(Supplier):
    name = "Global Fresh Trade"
    final_file = "Global Fresh Trade.xlsx"
    match_names = ["global fresh trade", "globalfreshtrade", "global fresh"]
    layout_hints = [r"unsere angebote", r"gr(?:ö|oe|o)sse\s*/\s*kal"]
    file_types = (".txt",)
    origin_style = "name"
    must_fill = ("WEIGHT (KG)",)  # when the list doesn't say the box weight: left empty, in red

    def parse(self, doc):
        rows, head, variety_hint = [], None, ""
        for raw in doc.text.splitlines():
            line = clean(raw)
            if not line or line.startswith("---") or re.search(r"(?i)good morning|pricelist|angebote", line):
                continue
            prices = list(PRICE_RE.finditer(line))
            if not prices:
                if describe(re.sub(NOISE, " ", line))["species"] or not re.search(r"\d", line) and len(line.split()) > 2:
                    head = self.read_product(line, head, variety_hint)     # a product (maybe not tracked)
                    variety_hint = ""
                elif not re.search(r"\d", line) and len(line.split()) <= 2:
                    variety_hint = line.strip(" :-")                     # 'Valencia' above the oranges
                continue
            first = line[:prices[0].start()]
            tail = line[prices[-1].end():]
            if head is None or describe(re.sub(NOISE, " ", first))["species"] or has_words(first):
                head = self.read_product(first + " " + tail, head, variety_hint)
                variety_hint = ""
                sizes = head["sizes"]
            else:
                sizes = self.sizes(first)
            if head is None:
                continue
            previous = sizes
            for i, m in enumerate(prices):
                text = line[prices[i - 1].end():m.start()] if i else ""
                detail = head["detail"]
                if i:
                    if re.search(r"(?i)\bby lorry\b|\blkw\b", text):
                        sizes, detail = previous, "By lorry"        # same sizes, the price by lorry
                    else:
                        sizes = self.sizes(text)
                previous = sizes
                weight, guessed = head["weight"], ()
                if weight is None and head["species"] in DEFAULT_WEIGHT:
                    weight, guessed = DEFAULT_WEIGHT[head["species"]], ("WEIGHT (KG)",)
                for size in sizes or ["N/S"]:
                    rows.append(self.row(
                        specie=head["species"], variety=head["variety"], origin=head["origin"], size=size,
                        weight=weight, cat=head["cat"], brand=head["brand"], box_pp=head["box_pp"],
                        packaging=box_material(head["species"], weight), price=N.to_number(m[1].replace(",", ".")),
                        detail=detail, type=head["type"], guessed=guessed))
        return rows

    @staticmethod
    def sizes(text):
        """'88' -> [88], '54/60 st' -> [54, 60], 'Grösse/Kal. 18' -> [18], 'Cal.1' -> [1], '65 +' -> ['65+']."""
        out = []
        text = re.sub(r"(?i)\d+(?:[.,]\d+)?\s*x\s*\d+(?:[.,]\d+)?\s*(?:kg|gr?|gram)\b|\d+(?:[.,]\d+)?\s*kg\b", " ", text or "")
        for m in SIZE_RE.finditer(text):
            for s in re.split(r"\s*/\s*", (m[1] or m[2]).replace(" ", "")):
                if s:
                    out.append(int(s) if s.isdigit() else s)
        return out

    def read_product(self, text, previous, variety_hint):
        """'Oranges Valencia cat 1 88' -> species, variety, origin, weight, cat, box pp, sizes, detail, type."""
        t = clean(text)
        kind = "BY AIR" if re.search(r"(?i)\bby air\b", t) else ""
        t = re.sub(r"(?i)\bby air\b", " ", t)
        detail = next((name for rx, name in DETAILS if re.search(rx, t)), "")
        for rx, _ in DETAILS:
            t = re.sub(rx, " ", t)
        t = re.sub(DROP, " ", t)
        m = CAT_RE.search(t)
        cat = ""
        if m:
            cat = {"1": "I", "2": "II"}.get(m[1], m[1].upper())
            t = t[:m.start()] + " " + t[m.end():]
        brand = next((b.title() for b in BRANDS if re.search(rf"(?i)\b{b}\b", t)), "")
        if brand:
            t = re.sub(rf"(?i)\b{brand}\b", " ", t)
        named = ("", "")
        for rx, what in NAMED.items():
            m = re.search(rf"(?i)\b{rx}\b", t)
            if m:
                brand, named = m[0].title(), what
                t = t[:m.start()] + " " + t[m.end():]
        t = re.sub(NOISE, " ", t)
        head = describe(t)
        rest = head["variety"]
        sizes = self.sizes(rest)
        rest = SIZE_RE.sub(" ", rest)
        kept = next((w.title() for w in VARIETY_WORDS if re.search(rf"(?i)\b{w}s?\b", t)), "")
        if head["species"]:
            for a in _aliases(head["species"]):          # 'Ingwer China Ginger': both names go
                rest = re.sub(rf"(?i)(?<!\w){re.escape(a)}(?!\w)", " ", rest)
        variety = re.sub(r"\s+", " ", re.sub(r"[^\w\s&'-]", " ", rest)).strip(" -")
        variety = variety.title() if variety.islower() or variety.isupper() else variety
        variety = " ".join(x for x in (kept, variety) if x) or named[0] or variety_hint
        origin = head["origin"] or named[1]
        same = previous and previous["species"] == head["species"] and variety in ("", previous["variety"])
        if not origin and same:
            origin = previous["origin"]                  # 'Oranges Valencia cat 1 88': still Zimbabwe
        if not variety and same:
            variety = previous["variety"]
        species = head["species"] or re.sub(r"\s+", " ", t).strip()   # untracked: listed as skipped
        return {"species": species, "variety": variety if head["species"] else "", "origin": origin,
                "weight": head["weight"], "cat": cat, "brand": brand, "box_pp": head["box_pp"],
                "sizes": sizes, "detail": detail or head["pack"] or "", "type": kind}

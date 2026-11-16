"""Unknown: prices from several sources whose supplier we don't know, collected in one text (usually
WhatsApp messages pasted into a .txt). The layout changes from one message to the next, so this reader
is flexible: a product heading, optionally a variety on its own line, then sizes and prices.

    *Nashi pear update :*                 heading: species (+ variety, origin)
    5kg size 14 = 1.5 pallets             sizes waiting for a price (weight, pallets)
    5kg size 18 = 0.5 pallets
    7.50€ / box                           a price without a size: for all the sizes above
    GGN 4052852334877                     (certificate number: not kept)

    *Mango Brazil update*
    Kent                                  a variety under the heading
    X 5.   1x280 : 6.25€                  size 5, 1 pallet of 280 boxes, 6.25
    Cal 7. 2x280 : 6.15€

    AVOCADO HASS MOROCCO                  (SOLY-like: 'SIZE 12/14 : 15.50€')
    SIZE 12/14 : 15.50€

Each new layout the team receives gets added here (see the examples in the docstring).
"""
import re

from .. import normalize as N
from ..base import Supplier, register
from ._common import box_material, clean, describe

FILLER = r"(?i)\b(?:update|updates|prices?|offer|today|stock|available|new)\b"
SIZE_RE = re.compile(r"(?i)(?:\bsize|\bcal(?:ibre|iber)?|(?<![\w.])x)\s*\.?\s*(\d+(?:\s*[/&+-]\s*\d+)*\+?|[SMLX]{1,3}L?)\b\.?")
PALLETS_RE = re.compile(r"(?i)(\d+(?:[.,]\d+)?)\s*(?:pallets?|plts?|pal)\b")
PALLET_BOXES_RE = re.compile(r"(?i)(?<![\d.,])(\d+(?:[.,]\d+)?)\s*x\s*(\d{2,3})(?!\s*(?:g|gr|kg)\b)")
WEIGHT_RE = re.compile(r"(?i)(?<![\d.,])(\d+(?:[.,]\d+)?)\s*kg\b")
PRICE_RE = re.compile(r"(?i)(?:€\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*(?:€|eur\b|euro))")
DEFAULT_WEIGHT = {"Mangoes": 4}         # box weight when the message doesn't say it
SKIP_RE = re.compile(r"(?i)^(?:ggn|gln|global ?gap|coc)\b")


def number(text):
    return N.to_number(str(text).replace(",", "."))


@register
class Unknown(Supplier):
    name = "Unknown"
    final_file = "Unknown.xlsx"
    match_names = ["unknown"]
    name_wins = True              # no identity of its own: a file called 'Unknown ...' is always read here
    file_types = (".txt", ".pdf")
    origin_style = "name"
    must_fill = ("WEIGHT (KG)",)  # when the message doesn't say the box weight: left empty, in red

    def parse(self, doc):
        rows, head, waiting = [], None, []
        for raw in doc.text.splitlines():
            line = clean(raw)
            if not line:
                waiting = []                            # a blank line ends a block
                continue
            if SKIP_RE.search(line):
                continue
            m = PRICE_RE.search(line)
            price = number(m[1] or m[2]) if m else None
            info = self.read_sizes(line[:m.start()] if m else line)
            if price is None:
                if info["size"] is not None:
                    waiting.append(info)                # '5kg size 14 = 1.5 pallets': price comes later
                elif head and len(line.split()) <= 3 and not describe(line)["species"]:
                    head = dict(head, variety=line.strip(" :-"))           # 'Kent' under 'Mango Brazil'
                else:
                    head = self.read_heading(line)
                continue
            if head is None or not head["species"]:
                continue
            if info["size"] is None and waiting:        # '7.50€ / box': for the sizes listed above
                targets, waiting = waiting, []
            else:
                targets = [info]
            for t in targets:
                weight = t["weight"] or head["weight"] or DEFAULT_WEIGHT.get(head["species"])
                rows.append(self.row(
                    specie=head["species"], variety=head["variety"], origin=head["origin"],
                    size=t["size"] if t["size"] is not None else "N/S", weight=weight,
                    box_pp=t["box_pp"] or head["box_pp"], packaging=box_material(head["species"], weight),
                    price=price, detail=t["detail"] or head["pack"] or "", type=head["type"]))
        return rows

    @staticmethod
    def read_heading(line):
        text = re.sub(FILLER, " ", line).strip(" :-")
        kind = ("BY AIR" if re.search(r"(?i)\bby air\b|\bair\s*freight\b", text) else
                "RTE" if re.search(r"(?i)\bready to eat\b|\brte\b", text) else "")
        text = re.sub(r"(?i)\bby air\b|\bair\s*freight\b|\bready to eat\b|\brte\b", " ", text)
        head = describe(text)
        v = head["variety"]
        head["variety"] = v.title() if v.isupper() or v.islower() else v       # HASS / nashi -> Hass / Nashi
        head["type"] = kind
        return head

    @staticmethod
    def read_sizes(text):
        """Size, weight, pallets and boxes per pallet in the part of a line before its price."""
        out = {"size": None, "weight": None, "box_pp": None, "detail": ""}
        m = WEIGHT_RE.search(text)
        if m:
            out["weight"] = number(m[1])
            text = text[:m.start()] + " " + text[m.end():]
        m = PALLET_BOXES_RE.search(text)
        if m:                                           # '2x280': 2 pallets of 280 boxes
            out["detail"], out["box_pp"] = f"{m[1]}x", int(m[2])
            text = text[:m.start()] + " " + text[m.end():]
        m = PALLETS_RE.search(text)
        if m:                                           # '= 1.5 pallets'
            out["detail"] = f"{m[1].replace(',', '.')}P"
            text = text[:m.start()] + " " + text[m.end():]
        m = SIZE_RE.search(text)
        if m:
            s = re.sub(r"\s+", "", m[1].upper())
            out["size"] = int(s) if s.isdigit() else s
        return out

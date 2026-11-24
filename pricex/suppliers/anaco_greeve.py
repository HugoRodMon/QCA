"""Anaco Greeve: pdf table.

    ARTICLE                   SIZE            Euro   ORIGIN BRAND   WEIGHT     C/PAL
    Oranges                                                                         <- section
    Navel Cambria T.C. (cat I) 72             15,50  RSA    JoRie   ca 15,0 kg 80
    Garlic (Pure white 50+)   20x500 GR       22,00  CN     Various ca 10,0 kg 100
    Pineapple (super sweet)   9               11,00  CR     Fyffes  ca 11,0 kg 80     <- variety Super Sweet
    Kent (by air)             10              33,50  PE ...                          <- TYPE By Air
    Garcima (yellow)          20B             6,50   RSA ...                         <- the flesh colour: not kept
    Clementine Nespack        1X              14,50  MA ...                          <- Clementine, DETAIL Nespack
"""
import re

from .. import normalize as N
from ..base import Supplier, register


@register
class AnacoGreeve(Supplier):
    name = "ANACO GREEVE"
    final_file = "ANACO GREEVE.xlsx"
    match_names = ["anaco"]
    match_text = ["anacogreeve", "anaco greeve"]
    layout_hints = [r"article\s+size\s+euro\s+origin\s+brand\s+weight\s+c/pal"]
    origin_style = "source"

    def parse(self, doc):
        rows, section, cut = [], "", None
        lines = doc.lines
        for i, line in enumerate(lines):
            words = [w.text for w in line.words]
            if words[:1] == ["ARTICLE"] and "Euro" in words:
                x = {w.text: w.x0 for w in line.words}
                # column borders, a bit left of each header (numbers are right-aligned)
                cut = [x["SIZE"] - 25, x["Euro"] - 6, x["ORIGIN"] - 6, x["BRAND"] - 12, x["WEIGHT"] - 6, x["C/PAL"] - 6]
                continue
            if cut is None:
                continue
            col = split(line, cut)
            price = N.parse_plain_price(col[2])
            if not col[2] and not col[1] and len(line.words) <= 3:
                nxt = lines[i + 1] if i + 1 < len(lines) else None
                if not (nxt and abs(nxt.top - line.top) < 2.5):          # hidden title printed over a row
                    at = {}
                    for w in line.words:                                 # two titles at the same place
                        at[round(w.x0)] = w.text                         # ('Bananas' under 'Oranges'): the last
                    section = " ".join(at.values())
                continue
            if price is None:
                continue                                             # POR
            rows.append(self.make_row(section, col, price))
        return rows

    def make_row(self, section, col, price):
        article, size_txt = col[0], re.sub(r"\(ETA[^)]*\)?", "", col[1]).strip()
        detail = N.box_type(article)
        cat = ""
        m = re.search(r"\(cat\s*(I{1,2})\)", article, re.I)
        if m:
            cat = m[1].upper()
        article = re.sub(r"\(cat[^)]*\)|\b[OT]\.[TC]\.", " ", article, flags=re.I)

        size, extra, kind = size_txt, "", ""
        if re.search(r"(?i)\(\s*by air\s*\)", article):                  # 'Kent (by air)'
            kind = "By Air"
            article = re.sub(r"(?i)\(\s*by air\s*\)", " ", article)
        article = re.sub(r"(?i)\(\s*(?:yellow|white|red)\s*\)", " ", article)   # nectarines' flesh colour
        if re.fullmatch(r"(?i)[\d,.]+\s*kg", size_txt):
            size = "N/S"                                              # "2KG" / "10 KG" is the box weight
        pack = N.pack_detail(size_txt)
        if pack:                                                      # "20x500 GR" is the packing
            size = "N/S"
            detail = detail or pack
        inner = re.search(r"\(([^)]*)\)", article)                   # "(Pure white 55+)", "(Royal Tioga)"
        if inner:
            m = re.search(r"\b(\d+\+)", inner[1])
            if m:
                size = m[1]
            extra = re.sub(r"\b\d+\+", "", inner[1]).strip()
            article = article[:inner.start()] + article[inner.end():]
        if re.search(r"(?i)super sweet", extra):
            extra = "Super Sweet"                                     # 'Pineapple (super sweet)'

        article = " ".join(article.split())
        species = N.find_species(article)
        variety = extra or article
        m = re.match(r"(?i)(clementines?)\s+(.+)", article)
        if species == "Mandarins" and m and not extra:
            # 'Clementine Nespack', 'Clementine pitufo', 'Clementine with leaf': the rest is about the box
            variety = "Clementine"
            detail = " ".join(x for x in (m[2].strip().title(), detail) if x)
        elif species and N.find_species(variety) == species:
            from ._common import remove_alias
            variety = remove_alias(variety, species)
        variety = variety.title() if extra or variety.islower() else variety          # 'peeled' -> 'Peeled'
        return self.row(
            specie=article if species else f"{article} {section}", variety=variety,
            origin=col[3], size=size or "N/S", price=price, brand=col[4], cat=cat,
            weight=N.to_number(col[5]), box_pp=N.to_number(col[6]), detail=detail, type=kind)


def split(line, cut):
    cols = [[] for _ in range(len(cut) + 1)]
    for w in line.words:
        i = sum(w.x0 >= c for c in cut)
        cols[i].append(w.text)
    return [" ".join(c) for c in cols]

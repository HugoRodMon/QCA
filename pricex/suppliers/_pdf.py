"""Helpers to read tables out of pdf lines (see readers.Line / readers.Word)."""
import re

from .. import normalize as N


class Columns:
    """Column positions taken from a header line.

    cols = Columns.from_header(line, ["Product", "Origin", "Brand", "Cat", "KG", "PP", "Size", "Remark", "Price"])
    cells = cols.split(data_line)   # {"Product": "Hass", "Origin": "Colombia", ...}
    """

    def __init__(self, starts, page_width=10_000):
        self.starts = sorted(starts, key=lambda c: c[1])      # [(name, x0)]
        self.width = page_width

    @classmethod
    def from_header(cls, line, names):
        starts = []
        words = line.words
        for name in names:
            parts = name.lower().split()
            for i in range(len(words) - len(parts) + 1):
                if [w.text.lower().strip(":") for w in words[i:i + len(parts)]] == parts:
                    starts.append((name, words[i].x0))
                    break
        return cls(starts)

    def split(self, line, slack=4):
        """Text per column: a word belongs to the last column that starts before it."""
        out = {name: [] for name, _ in self.starts}
        for w in line.words:
            name = None
            for n, x0 in self.starts:
                if w.x0 >= x0 - slack:
                    name = n
            if name:
                out[name].append(w.text)
        return {k: " ".join(v) for k, v in out.items()}


def is_header(line, *words):
    t = line.text.lower()
    return all(w.lower() in t for w in words)


def cells(words, gap=3.5):
    """Group the words of a line into cells: words closer than `gap` points belong together
    ('€', '1', '3,25' -> one cell '€ 1 3,25')."""
    out = []
    for w in words:
        red = getattr(w, "red", False)
        if out and w.x0 - out[-1]["x1"] <= gap:
            out[-1]["text"] += " " + w.text
            out[-1]["x1"] = w.x1
            out[-1]["red"] = out[-1]["red"] or red
        else:
            out.append({"text": w.text, "x0": w.x0, "x1": w.x1, "red": red})
    for c in out:
        c["xc"] = (c["x0"] + c["x1"]) / 2
    return out


def price_cells(words, gap=3.5):
    """Cells of a grid row that hold a price or a 'no price' marker (POR, exp, dates...)."""
    out = []
    for c in cells(words, gap):
        t = c["text"]
        if "€" in t:
            for part in re.findall(r"€\s*[\d ]+[.,]?\d*", t):     # "€ 13,00 € 13,00" glued together
                out.append(dict(c, text=part, price=N.parse_price(part)))
        else:
            out.append(dict(c, price=N.parse_plain_price(t)))
    return out


def nearest(x, targets, max_dist=40):
    """Index of the target x closest to x (or None if all are too far)."""
    best = None
    for i, t in enumerate(targets):
        d = abs(t - x)
        if d <= max_dist and (best is None or d < best[1]):
            best = (i, d)
    return best[0] if best else None

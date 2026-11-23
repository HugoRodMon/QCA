"""The pasted report -> a clean Report.

The website's page (or the same report pasted into Excel first) comes as a grid of cells. On top, the summary:
pairs of 'Label:' and value ('Business partner:' 'Fresh Pride'). Below, the boxes table: a header row whose
names are often pictures of rotated text, then one row per box. The first columns are the website's
Edit/Copy/Delete links, not data.

A cell, as the screen sends it: {"t": text, "img": [{"src", "alt", "title"}], "links": n}.
"""
import re
from dataclasses import dataclass, field

# the website's columns before and after the defects (any other column with percentages is a defect)
ACTIONS = ("edit", "copy", "delete")
NOT_DEFECTS = {"1st cat", "2nd cat", "non standard", "waste", "blush less 50%", "blush 50 - 70%", "blush 50-70%",
               "blush above 70%", "first appearance", "shelf life", "insp.crtns", "insp. crtns"}
# the names the website uses: a picture read with OCR is snapped to the closest one
KNOWN_COLUMNS = [
    "Edit", "Copy", "Delete", "Product", "Variety", "Brand", "Category", "Packaging", "Count", "Temperature",
    "Weight 1", "Weight 2", "First appearance", "Brix 1", "Brix 2", "Pressure 1", "Pressure 2", "Blush less 50%",
    "Blush 50 - 70%", "Blush above 70%", "Bruises", "Dehydration", "Open injuries", "Skin defects", "Sunburn",
    "Bitterpit", "Decay", "Lenticel", "1st cat", "2nd cat", "Non standard", "Waste", "Remarks", "Shelf life",
    "Insp.Crtns", "Deformed", "Handling damages", "Packing damages", "Mechanical damages", "Russeting", "Scab",
    "Oily skin", "Lack of colour", "Low temperature damages", "Mould on blossom end", "Mould on stem", "Scald",
    "Watercore", "Cracking", "Bulls eye", "Under colour", "Undersize", "Dust", "Misshapen", "Frost damage",
    "Shriveling", "Insect damages", "Internal breakdown", "Freezing damage", "Mould", "Size", "Colour",
]


@dataclass
class Report:
    summary: dict = field(default_factory=dict)       # 'Business partner' -> 'Fresh Pride'
    columns: list = field(default_factory=list)       # the boxes table's column names (None: not known yet)
    boxes: list = field(default_factory=list)         # one dict per box: column name -> value
    raw: list = field(default_factory=list)           # the boxes' cells as pasted (for columns named later)
    pictures: list = field(default_factory=list)      # per column: the header cell's pictures (to read them)
    problems: list = field(default_factory=list)

    @property
    def template_name(self):
        return self.summary.get("Template name", "")

    def column_values(self, name):
        return [b.get(name) for b in self.boxes]

    def first(self, name):
        return next((v for v in self.column_values(name) if v not in (None, "")), "")

    @property
    def defects(self):
        """[(name, average over the boxes where it was found, boxes with it, average over all boxes)]."""
        out = []
        for name in self.columns:
            if not name or name.lower() in NOT_DEFECTS:
                continue
            values = self.column_values(name)
            if not any(isinstance(v, Percent) for v in values):
                continue
            found = [float(v) for v in values if isinstance(v, Percent) and float(v) > 0]
            total = sum(float(v) for v in values if isinstance(v, Percent))
            out.append((name, sum(found) / len(found) if found else 0.0, len(found), total / max(len(values), 1)))
        return out


class Percent(float):
    """A value the report writes as a percentage ('4.30%' -> 4.3)."""


def clean(text):
    return re.sub(r"\s+", " ", str(text or "").replace("\xa0", " ")).strip()


def value(text):
    """'4.30%' -> Percent(4.3), '17850' -> 17850, '2.3' -> 2.3, '-' -> '', the rest as text."""
    t = clean(text)
    if t in ("-", "—"):
        return ""
    m = re.fullmatch(r"(-?\d+(?:[.,]\d+)?)\s*%", t)
    if m:
        return Percent(float(m[1].replace(",", ".")))
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+[.,]\d+", t):
        return float(t.replace(",", "."))
    return t


def is_link(cell):
    t = clean(cell.get("t"))
    return not t or t.lower().startswith(("http://", "https://")) or t.lower() in ACTIONS


def read(grid, names=None, layouts=None):
    """grid: rows of cells as the screen sends them. names(cell) -> a column name read from the header cell's
    pictures (or None). layouts: {template name: [column names]} remembered from earlier pastes."""
    report = Report()
    rows = [[c if isinstance(c, dict) else {"t": c} for c in row] for row in grid]

    # the summary: 'Label:' followed by its value, anywhere above the table
    header_at = None
    for i, row in enumerate(rows):
        if _looks_like_header(row):
            header_at = i
            break
        for j, cell in enumerate(row):
            t = clean(cell.get("t"))
            if t.endswith(":") and len(t) > 1:
                label = t[:-1].strip()
                v = clean(row[j + 1].get("t")) if j + 1 < len(row) else ""
                if label and label != "-" and not v.endswith(":"):
                    report.summary[label] = "" if v in ("-", "—") else v
                elif label and label != "-":
                    report.summary[label] = ""
    if header_at is None:                                 # no header row: the first row with several values
        header_at = next((i for i, r in enumerate(rows) if sum(1 for c in r if not is_link(c)) >= 5), None)
        if header_at is None:
            report.problems.append("no boxes table found in what was pasted")
            return report
        header_at -= 1                                    # (the header row is missing: all rows are boxes)
        header = []
    else:
        header = rows[header_at]

    body = [r for r in rows[header_at + 1:] if sum(1 for c in r if not is_link(c)) >= 3]
    # the header's names: its text, or what its pictures say
    columns = []
    for cell in header:
        t = clean(cell.get("t"))
        name = None
        if t and not t.startswith("#") and not t.lower().startswith("http"):
            known = snap(t)                       # the website's capitals, but its spelling as written
            name = known if known and known.lower() == t.lower() else t
        elif names and cell.get("img"):
            name = names(cell)
        columns.append(name)
    pictures = [cell.get("img") or [] for cell in header]

    # line the header up with the boxes: drop the Edit/Copy/Delete columns (links, icons) on both sides
    while columns and (columns[0] is None or columns[0].lower() in ACTIONS) and _all_links(body, 0, len(columns)):
        columns.pop(0)
        pictures.pop(0)
        body = [r[1:] if len(r) > len(columns) else r for r in body]
    body = [_drop_leading_links(r, len(columns)) for r in body]
    width = max([len(columns)] + [len(r) for r in body])
    columns += [None] * (width - len(columns))
    pictures += [[]] * (width - len(pictures))

    # names still missing: the layout remembered for this website template (same number of columns)
    known = (layouts or {}).get(report.summary.get("Template name", ""))
    # and names typed in by hand win over what the pictures say: the website cuts long names short
    # ('Dry stem (slight mo'), so a remembered name that starts the same is the full one
    if known and len(known) == len(columns):
        def fits(read, kept):
            if not read or not kept:
                return True
            a, b = read.lower().rstrip(" .…"), kept.lower()
            return a == b or b.startswith(a)
        if sum(1 for c, k in zip(columns, known) if fits(c, k)) >= 0.8 * len(columns):
            columns = [k or c for c, k in zip(columns, known)]

    report.columns, report.pictures = columns, pictures
    report.raw = [[clean(c.get("t")) for c in r] + [""] * (width - len(r)) for r in body]
    fill(report)
    return report


def fill(report):
    """The boxes from the raw cells and the column names (again after a name is typed in)."""
    report.boxes = []
    for raw in report.raw:
        box = {}
        for name, text in zip(report.columns, raw):
            if name:
                box[name] = value(text)
        report.boxes.append(box)
    missing = sum(1 for c in report.columns if not c)
    report.problems = [p for p in report.problems if "column name" not in p]
    if missing:
        report.problems.append(f"{missing} column name{'s' if missing > 1 else ''} couldn't be read: type them in")


def snap(text):
    """A column name as the website writes it ('bruises' -> 'Bruises'), or None if it isn't one we know."""
    key = re.sub(r"[^a-z0-9%]", "", text.lower())
    for name in KNOWN_COLUMNS:
        if re.sub(r"[^a-z0-9%]", "", name.lower()) == key:
            return name
    return None


def _looks_like_header(row):
    texts = [clean(c.get("t")).lower() for c in row]
    pictures = sum(1 for c in row if c.get("img") and not clean(c.get("t")))
    known = sum(1 for t in texts if snap(t))
    return known >= 4 or pictures >= 5 or sum(1 for t in texts if t in ("#value!", "#¡valor!")) >= 5


def _all_links(body, j, width):
    return all(j < len(r) and is_link(r[j]) for r in body if len(r) >= width) if body else True


def _drop_leading_links(row, width):
    """Box rows that have more leading link cells than the header (Excel splits the website's arrows)."""
    row = list(row)
    while len(row) > width and is_link(row[0]):
        row.pop(0)
    return row

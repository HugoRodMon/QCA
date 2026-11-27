"""A template with [placeholders] + a report -> the remark, and one line per box.

A template (data/templates.json, or the shared copy):
    {"client": "Fresh Pride", "product": "Apples",
     "remark": "The inspection was carried out on [date] in [place]. ...",
     "box": "[weight check]",                       one line per box ("" = no box lines)
     "categories": {"2nd cat": [...], "non standard": [...], "waste": [...]},   optional: which defect goes where
     "grade": {"tables": {name: [[from %, grade], ...]}, "defects": {defect: table name}}}   optional

Placeholders are case-insensitive. Every summary label works as one ([business partner], [vessel name],
[temptale]...), and so does every column of the boxes table ([variety], [count]...). The computed ones are in
PLACEHOLDERS below.
"""
import math
import re
from datetime import datetime

from .report import Percent

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
# the computed placeholders, with what they give (shown in the app as help)
PLACEHOLDERS = {
    "date": "inspection date, as 'november 17th'",
    "week": "inspection week",
    "place": "inspection place (or position and destination: 'Shanghai, China')",
    "origin": "origin",
    "variety": "varieties, joined ('Gala and Fuji')",
    "varieties": "the varieties with the word: 'Gala variety', 'Gala and Fuji varieties'",
    "brand": "brands / labels",
    "box weight": "declared box weight in kg ('18.0')",
    "package": "the pack as written ('12x125g'), or the box weight ('18.0 kg')",
    "packages": "every packaging, whole: '10.0 kg plastic boxes and 4.0 kg carton boxes'",
    "box type": "the box: carton, plastic...",
    "defects": "the ticked defects with their average incidence",
    "defects range": "the ticked defects with their lowest and highest % ('decay (0.0 - 3.5%)')",
    "defects name": "the ticked defects, names only: 'bruises, dehydration and decay'",
    "quality defects": "'an average of 6.64% quality defects' (the Quality group's non-zero values)",
    "condition defects": "'an average of 5.69% condition defects' (the Condition group's non-zero values)",
    "quality defects %": "the Quality group's average alone: '6.64'",
    "condition defects %": "the Condition group's average alone: '5.69'",
    "defects by grower": "for each grower, its ticked defects with their range: 'grower D14914, skin defects (0.0 - 3.8%) ... and grower D6827, ...'",
    "temperature recorder": "'Temperature recorder is attached to the report.' (or 'recorders are', or 'was not found.')",
    "boxes": "number of boxes inspected",
    "average weight": "average net weight of the boxes, in g",
    "weight summary": "'The average weight recorded for the 18.0 kg samples was 18150 g and does not show underweight.'",
    "1st cat": "average 1st category %",
    "2nd cat": "average 2nd category %",
    "non standard": "average non standard %",
    "waste": "average waste %",
    "grade": "final grade (templates with a grade table)",
}
BOX_PLACEHOLDERS = {
    "box": "the box number",
    "net weight": "its net weight, in g",
    "weight check": "'The sample shows a 0.83% underweight, equivalent to 150g below the declared box weight.'",
    "underweight %": "how much under the declared weight, in %",
    "underweight g": "how much under the declared weight, in g",
}
NET_WEIGHT = ("Weight 1", "Net weight", "Weight")
PLACEHOLDER = re.compile(r"\[([^\[\]\n]{1,40})\]")


def number(x, digits=2):
    """Like Excel's ROUND, shown without trailing zeros past one decimal: 83.175 -> 83.18, 0.70 -> 0.7, 5 -> 5."""
    if isinstance(x, int):
        return str(x)
    r = math.floor(abs(x) * 10 ** digits + 0.5 + 1e-9) / 10 ** digits * (1 if x >= 0 else -1)
    return str(int(r)) if digits == 0 else str(round(r, digits))


def joined(items, word="and"):
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {word} " + items[-1]


def unique(values):
    seen = []
    for v in values:
        v = str(v).strip() if v not in (None, "") else ""
        if v and v not in seen:
            seen.append(v)
    return seen


# packs: 12x125g, 8*400g, 6×1kg (always written back with an x)
PACK = re.compile(r"(?i)(\d+)\s*[x*×]\s*(\d+(?:[.,]\d+)?)\s*(kg|gr?|grams?)\b")


def box_weight(report, packaging=None):
    """The declared box weight in kg, from the packaging ('18 kg carton box' -> 18.0, '12x125g' -> 1.5).
    Without a packaging: the report's first one."""
    packaging = str(report.first("Packaging") if packaging is None else packaging)
    m = PACK.search(packaging)
    if m:
        each = float(m[2].replace(",", "."))
        return round(int(m[1]) * each / (1 if m[3].lower() == "kg" else 1000), 3)
    m = re.search(r"(?i)(\d+(?:[.,]\d+)?)\s*kg", packaging)
    return float(m[1].replace(",", ".")) if m else None


def package(report, packaging=None):
    """'12x125g' as written for packs; '18.0 kg' for a box."""
    packaging = str(report.first("Packaging") if packaging is None else packaging)
    m = PACK.search(packaging)
    if m:
        unit = "kg" if m[3].lower() == "kg" else "g"
        return f"{m[1]}x{m[2].replace(',', '.')}{unit}"
    kg = box_weight(report, packaging)
    return f"{kg:.1f} kg" if kg is not None else ""


def box_type(packaging):
    """'10kg plastic box' -> 'plastic'; carton when it doesn't say."""
    m = re.search(r"(?i)(?:kg|g|gr)\.?\s*([a-z]+)", str(packaging or ""))
    return m[1].lower() if m and m[1].lower() not in ("box", "boxes") else "carton"


def packages(report):
    """Every packaging in the report: '10.0 kg plastic boxes and 4.0 kg carton boxes'."""
    out = []
    for p in unique(report.column_values("Packaging")):
        text = f"{package(report, p)} {box_type(p)} boxes".strip()
        if text not in out:
            out.append(text)
    return joined(out)


def place(report):
    """The inspection place; templates like Avocados - Westfalia give Position and Destination instead."""
    s = report.summary
    if s.get("Inspection Place"):
        return s["Inspection Place"]
    dest = s.get("Destination", "")
    dest = dest.title() if dest.isupper() else dest                  # 'CHINA' -> 'China'
    return ", ".join(x for x in (s.get("Position", ""), dest) if x)


def net_weights(report):
    name = next((n for n in NET_WEIGHT if n in report.columns), None)
    return [b.get(name) for b in report.boxes] if name else []


def inspection_date(report):
    text = report.summary.get("Inspection Date", "")
    m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text)
    if not m:
        return None
    try:
        return datetime(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None


def ordinal(n):
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def categories(report, template):
    """Average 1st cat / 2nd cat / non standard / waste %. With the template's defect -> category list they're
    worked out from the defects (as Fresh Pride's sheet does); without it, the report's own columns are used."""
    groups = (template or {}).get("categories")
    out = {}
    if groups:
        per_box = {k: [] for k in ("1st cat", "2nd cat", "non standard", "waste")}
        for box in report.boxes:
            sums = {k: sum(float(box.get(d) or 0) for d in groups.get(k, []) if isinstance(box.get(d), (int, float)))
                    for k in ("2nd cat", "non standard", "waste")}
            for k, v in sums.items():
                per_box[k].append(v)
            per_box["1st cat"].append(100 - sum(sums.values()))
        for k, values in per_box.items():
            out[k] = sum(values) / len(values) if values else None
        return out
    for k, column in (("1st cat", "1st cat"), ("2nd cat", "2nd cat"), ("non standard", "Non standard"), ("waste", "Waste")):
        values = [float(v) for v in report.column_values(column) if isinstance(v, (int, float))]
        out[k] = sum(values) / len(values) if values else None
    return out


def grade(report, template):
    """Each box's grade is its worst defect's (by the template's tables); the final grade is their average."""
    g = (template or {}).get("grade")
    if not g:
        return None
    grades = []
    for box in report.boxes:
        marks = []
        for defect, table_name in g["defects"].items():
            v = box.get(defect)
            table = g["tables"].get(table_name)
            if not table or not isinstance(v, (int, float)) or v <= 0:
                continue
            fitting = [row for row in table if row[0] <= v]            # Excel's XLOOKUP 'exact or next smaller'
            if fitting:
                best = max(r[0] for r in fitting)
                marks.append(next(r[1] for r in table if r[0] == best))
        grades.append(min(marks) if marks else max(r[1] for t in g["tables"].values() for r in t))
    return sum(grades) / len(grades) if grades else None


GROUPS = ("quality", "condition")
GROWER = ("Grower", "Grower nr", "Grower code", "Ggn grower")


def group_average(report, names):
    """The average of every non-zero value of these defects over all the boxes (as Camposol's remarks): 6.64."""
    values = [float(x) for name in names for x in report.column_values(name)
              if isinstance(x, (int, float)) and float(x) > 0]
    return sum(values) / len(values) if values else None


def by_grower(report, chosen=None):
    """'grower D14914, skin defects (0.0 - 3.8%) and decay (0.0 - 0.9%) and grower D6827, ...': for each grower,
    the ticked defects found in its boxes, with their lowest and highest %."""
    column = next((c for c in report.columns if c and c.lower() in [g.lower() for g in GROWER]), None)
    if not column:
        return ""
    growers = unique(report.column_values(column))
    parts = []
    for grower in growers:
        boxes = [b for b in report.boxes if str(b.get(column, "")).strip() == grower]
        found = []
        for name, _, n, _ in report.defects:
            if not n or (chosen is not None and name not in chosen):
                continue
            values = [float(b[name]) for b in boxes if isinstance(b.get(name), (int, float))]
            if values and max(values) > 0:
                found.append(f"{name.lower()} ({min(values):.1f} - {max(values):.1f}%)")
        if found:
            parts.append(f"grower {grower}, " + joined(found))
    return " and ".join(parts)


def values(report, template, chosen=None, custom=None, groups=None):
    """Every placeholder's text for this report. chosen: the defects to name in [defects] (None: all found).
    custom: {name: text} placeholders made by the admin; their text can use the other placeholders.
    groups: {defect name (lowercase): 'quality' | 'condition'}."""
    v = _values(report, template, chosen)
    for group in GROUPS:                                 # Camposol: 'an average of 6.64% quality defects'
        names = [n for n, _, _, _ in report.defects if (groups or {}).get(n.lower()) == group]
        avg = group_average(report, names)
        v[f"{group} defects %"] = number(avg) if avg is not None else "0"
        v[f"{group} defects"] = (f"an average of {number(avg)}% {group} defects" if avg is not None
                                 else f"no {group} defects")
    v["defects by grower"] = by_grower(report, chosen)
    for _ in range(3):                                   # a custom one may use another custom one
        for name, text in (custom or {}).items():
            key = re.sub(r"\s+", " ", name).strip().lower()
            if key:
                v[key] = fill(text, v)[0]
    return v


def _values(report, template, chosen=None):
    v = {}
    for label, text in report.summary.items():
        v[label.lower()] = text
    for name in report.columns:
        if name:
            v.setdefault(name.lower(), joined(unique(report.column_values(name))))
    day = inspection_date(report)
    if day:
        v["date"] = f"{MONTHS[day.month - 1]} {ordinal(day.day)}"
    m = re.search(r"(?i)wk\.?\s*(\d+)", report.summary.get("Inspection Date", ""))
    v["week"] = m[1] if m else ""
    v["place"] = place(report)
    v["origin"] = report.summary.get("Origin", "")
    names = unique(report.column_values("Variety"))
    v["variety"] = joined(names)
    v["varieties"] = f"{joined(names)} {'variety' if len(names) == 1 else 'varieties'}" if names else ""
    v["brand"] = joined(unique(report.column_values("Brand")))
    kg = box_weight(report)
    v["box weight"] = f"{kg:.1f}" if kg is not None else ""
    v["package"] = package(report)
    v["box type"] = box_type(report.first("Packaging"))
    v["packages"] = packages(report)
    found = [(name, avg) for name, avg, n, _ in report.defects if n]
    if chosen is not None:
        found = [(name, avg) for name, avg in found if name in chosen]
    v["defects"] = joined([f"{name.lower()} ({number(avg)}%)" for name, avg in found]) or "none"
    v["defects name"] = joined([name.lower() for name, _ in found]) or "none"     # 'bruises, decay and scars'
    ranges = []
    for name, _ in found:                                # lowest and highest over all the boxes
        values_ = [float(x) for x in report.column_values(name) if isinstance(x, (int, float))]
        ranges.append(f"{name.lower()} ({min(values_):.1f} - {max(values_):.1f}%)")
    v["defects range"] = joined(ranges) or "none"
    temptale = re.sub(r"[^\d]", "", report.summary.get("Temptale", "") or "")
    count = int(temptale) if temptale else 0
    v["temperature recorder"] = ("Temperature recorder was not found." if not count else
                                 "Temperature recorder is attached to the report." if count == 1 else
                                 "Temperature recorders are attached to the report.")
    v["boxes"] = str(len(report.boxes))
    weights = [w for w in net_weights(report) if isinstance(w, (int, float))]
    v["average weight"] = str(int(sum(weights) / len(weights))) if weights else ""
    if weights and kg:                                   # as the Fresh Pride sheet writes it
        avg = int(sum(weights) / len(weights))
        v["weight summary"] = (f"The average weight recorded for the {kg:.1f} kg samples was {avg} g"
                               + (" and does not show underweight." if kg * 1000 - avg <= 0 else "."))
    else:
        v["weight summary"] = ""
    for k, avg in categories(report, template).items():
        v[k] = number(avg) if avg is not None else ""
    g = grade(report, template)
    v["grade"] = number(g, 0) if g is not None else ""
    return v


def box_values(report, i, kg):
    box = report.boxes[i]
    v = {k.lower(): (number(float(x)) if isinstance(x, Percent) else str(x)) for k, x in box.items() if x not in (None, "")}
    v["box"] = str(i + 1)
    net = next((box.get(n) for n in NET_WEIGHT if isinstance(box.get(n), (int, float))), None)
    v["net weight"] = str(net) if net is not None else ""
    if net is not None and kg:
        under = kg * 1000 - net
        under = int(under) if float(under).is_integer() else round(under, 1)
        pct = under * 100 / (kg * 1000)
        v["underweight g"] = str(max(under, 0))
        v["underweight %"] = number(max(pct, 0))
        v["weight check"] = ("The sample shows a 0.0% underweight." if under <= 0 else
                             f"The sample shows a {number(pct)}% underweight, equivalent to {under}g below the declared box weight.")
    return v


def fill(text, v):
    """Replace the placeholders. Returns (text, [placeholders not known])."""
    unknown = []

    def put(m):
        key = re.sub(r"\s+", " ", m[1]).strip().lower()
        if key in v:
            return v[key]
        if m[0] not in unknown:
            unknown.append(m[0])
        return m[0]
    return PLACEHOLDER.sub(put, text or ""), unknown


def render(template, report, remark=None, box=None, chosen=None, custom=None, groups=None):
    """{'text', 'boxes': [lines], 'unknown': [placeholders], 'values': {placeholder: text}}."""
    v = values(report, template, chosen, custom, groups)
    text, unknown = fill(template.get("remark", "") if remark is None else remark, v)
    lines = []
    box_text = template.get("box", "") if box is None else box
    if box_text.strip():
        for i in range(len(report.boxes)):
            kg = box_weight(report, report.boxes[i].get("Packaging", report.first("Packaging")))
            line, missing = fill(box_text, {**v, **box_values(report, i, kg)})
            lines.append(line)
            unknown += [m for m in missing if m not in unknown]
    return {"text": text, "boxes": lines, "unknown": unknown, "values": v}


def pick(templates, client, product):
    """The template for a client and product: exact, then the client's for any product, then the product's
    for any client, then the default."""
    def norm(s):
        return re.sub(r"\s+", " ", str(s or "")).strip().lower()
    c, p = norm(client), norm(product)
    for want_c, want_p in ((c, p), (c, "*"), ("*", p), ("*", "*")):
        for t in templates:
            if norm(t.get("client")) == want_c and norm(t.get("product")) == want_p:
                return t
    return {"client": "*", "product": "*", "remark": "", "box": ""}

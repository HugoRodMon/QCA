"""China prices: the cleaned WeChat market reports (Word files) split into the columns of the China sheets.

The Word file is a list of headings and WeChat lines, as the team cleans them (see their tutorial,
"Precios para digitar"):

    Shanghai                                          <- market (REGION)
    2026/10/11 Shanghai Domestic Blueberries          <- date, and maybe the product
    South African orange: 2C                          <- product, origin, transport
    煜谦/1C/REDERBERG/MIDKNIGHT/15KG/CARTON/⇥56#64#60开⇥走1柜
    <general: seller/volume/brand/variety/weight...> TAB <sizes and prices> TAB <comment: how it sold>

Each line becomes a row of its product's sheet (CHERRIES, BLUEBERRY, CITRUS...) with the same columns as
"PLANILLA PRECIOS PARA DIGITAR.xlsx", so the rows can be pasted straight in. A line without its tabs is split
by guessing and listed to check; if its prices can't be found, it's listed for the person to add the tabs.
"""
import difflib
import html
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "data"
SHEETS = json.loads((DATA / "china_sheets.json").read_text(encoding="utf-8"))
# varieties already typed in each sheet: to split 'FORTUNESWEET ARYANA' (no slash) into brand and variety
VARIETIES = json.loads((DATA / "china_varieties.json").read_text(encoding="utf-8"))

# markets: heading words -> REGION. A new market is one more line here.
REGIONS = {"shanghai": "SH", "上海": "SH", "guangzhou": "GZ", "广州": "GZ", "gaobeidian": "GBD", "高碑店": "GBD",
           "jiaxing": "JX", "嘉兴": "JX"}
CODES = {"SH", "GZ", "GBD", "JX"}                    # the same markets as headings write them for short

# product words in a heading -> (ITEM, sheet). The first that matches wins ('Cherry+Berry' is cherries).
ITEMS = [
    (r"cherr|车厘子|樱桃", "CHERRIES", "CHERRIES"),
    (r"blueberr|蓝莓", "BLUEBERRIES", "BLUEBERRY"),
    (r"mandarin|tangerine|murcott|nadorcott|柑|橘", "MANDARINS", "CITRUS"),
    (r"grapefruit|西柚", "GRAPEFRUITS", "CITRUS"),
    (r"lemon|柠檬", "LEMONS", "CITRUS"),
    (r"orange|橙", "ORANGES", "CITRUS"),
    (r"avocado|牛油果", "AVOCADOS", "AVOCADO"),
    (r"grape|葡萄", "GRAPES", "GRAPES"),
    (r"pear|梨", "PEARS", "PEARS"),
    (r"apple|苹果", "APPLES", "APPLES"),
    (r"kiwi|猕猴桃|奇异果", "KIWI", "KIWI"),
    (r"plum|prune|李", "PLUMS", "STONEFRUIT"),
    (r"nectarine|油桃", "NECTARINES", "STONEFRUIT"),
    (r"apricot|杏", "APRICOTS", "STONEFRUIT"),
    (r"peach|桃", "PEACHES", "STONEFRUIT"),
    (r"mango|芒果", "MANGOES", "MANGO"),
    (r"pineapple|凤梨|菠萝", "PINNEAPPLES", "PINNEAPPLES"),
]
COUNTRIES = {"chile": "CHILE", "智利": "CHILE", "peru": "PERU", "秘鲁": "PERU", "south africa": "SOUTH AFRICA",
             "南非": "SOUTH AFRICA", "egypt": "EGYPT", "埃及": "EGYPT", "australia": "AUSTRALIA", "澳": "AUSTRALIA",
             "new zealand": "NEW ZEALAND", "新西兰": "NEW ZEALAND", "argentina": "ARGENTINA", "spain": "SPAIN",
             "morocco": "MOROCCO", "usa": "USA", "美国": "USA", "mexico": "MEXICO", "墨西哥": "MEXICO",
             "canada": "CANADA", "加拿大": "CANADA", "kenya": "KENYA", "肯尼亚": "KENYA", "colombia": "COLOMBIA",
             "turkey": "TURKEY", "italy": "ITALY", "greece": "GREECE", "brazil": "BRAZIL", "uruguay": "URUGUAY"}
PROVINCES = {"云南": "YUNNAN", "四川": "SICHUAN", "山东": "SHANDONG", "辽宁": "LIAONING", "贵州": "GUIZHOU",
             "广西": "GUANGXI", "海南": "HAINAN", "陕西": "SHAANXI", "新疆": "XINJIANG", "浙江": "ZHEJIANG"}
AIR = r"(?i)\bair|空运"
SEA = r"(?i)ocean|\bsea\b|shipping|海运"
# a product heading starts with these, unless it says otherwise ('Chilean air-freight cherries', 'Domestic ...')
ITEM_DEFAULTS = {"CHERRIES": ("AIR", "CHILE"), "BLUEBERRIES": ("OCEAN", "")}
# what a product's lines usually leave out (the team writes these themselves)
DEFAULT_WEIGHT = {"BLUEBERRIES": 1.5}
DEFAULT_PACKAGE = {"CHERRIES": "CARTON", "BLUEBERRIES": "Carton"}
MUST_HAVE_WEIGHT = {"CHERRIES"}                      # left empty and red when the line doesn't say it

NUMBER = r"\d+(?:\.\d+)?"
RANGE = rf"{NUMBER}(?:\s*-\s*{NUMBER})?"
# the sizes each sheet writes (the rest of the sheets: 56#, 1X, 4J...; plain numbers are sizes by position)
SIZES = {
    "CHERRIES": r"\d+(?:\.\d+)?D|XL{1,2}D{0,2}|L{1,2}D{0,2}|\d?J{1,2}[DL]{0,2}D?",
    "BLUEBERRY": r"\d{2}\+",
    "GRAPES": r"XL|SJ|\d?J{1,2}|S{0,2}X{1,2}V?|S{1,2}[PVX]|EP|A{1,3}|L|M",      # longest first: XL before X
    "_": r"\d{1,3}#|XL|\d?J{1,2}D{0,2}|\d?X{1,2}|A{1,3}|[SMLP]",
}
MIX = r"MIX|不分规格|统价|统果|通货|ALL ?SIZES?"     # one price for every size
NOISE = r"想定|不超|卖(?=\d)|(?<=\d)块|左右|约(?=\d)"   # 'expected', 'not over', 'sells at', 'yuan': not prices
VOLUME = re.compile(rf"^({NUMBER})\s*([PC板件柜])\s*(.*)$", re.I)


@dataclass
class Row:
    sheet: str
    values: dict = field(default_factory=dict)       # column heading -> value
    red: set = field(default_factory=set)            # headings to colour red (missing, to check)
    line: str = ""


@dataclass
class Report:
    rows: list = field(default_factory=list)
    unread: list = field(default_factory=list)       # (line, why) lines with prices that couldn't be read
    notes: list = field(default_factory=list)        # (line, what to check) read, but worth a look


# ---------------------------------------------------------------- reading the Word file

def read_docx(path):
    """The paragraphs, with their tabs as \\t (the team's separators)."""
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    lines = []
    for paragraph in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        bits = re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>|(<w:tab/>)|(<w:br/>)", paragraph)
        text = "".join(t if t else ("\t" if tab else " ") for t, tab, _ in bits)
        lines.append(html.unescape(text).strip(" "))
    return lines


def normalise(text):
    """Full-width signs to plain ones, so the rest only deals with one kind (tabs are kept)."""
    table = str.maketrans({"，": ",", "、": ",", "；": ";", "：": ":", "（": "(", "）": ")", "×": "*", "／": "/",
                           "＋": "+", "－": "-", "～": "-", "~": "-", "＃": "#", "　": " "})
    return re.sub(r"[  ]+", " ", text.translate(table)).strip()


# ---------------------------------------------------------------- headings

def read_heading(line, state, year):
    """Update the market / date / product from a heading line. Returns True if it was one."""
    low = line.lower()
    found = False
    region = None
    for word, code in REGIONS.items():
        if re.search(rf"(?<![a-z]){word}(?![a-z])", low) if word.isascii() else word in line:
            region = code
    if not region:
        codes = [c for c in re.findall(r"\b[A-Z]{2,3}\b", line) if c in CODES]
        if codes:
            region = codes[0]
    if not region and re.fullmatch(r"[a-zA-Z]{5,12}", line.strip()):      # 'Guanzhu': a market misspelt
        close = difflib.get_close_matches(low.strip(), [w for w in REGIONS if w.isascii()], n=1, cutoff=0.75)
        region = REGIONS[close[0]] if close else None
    if region and len(line) <= 70:
        if region != state.get("region") or re.fullmatch(r"[a-zA-Z ]+", line.strip()):
            for k in ("item", "sheet", "transport", "origin", "new"):     # a new market's report starts over
                state.pop(k, None)
        state["region"] = region
        found = True
    m = re.search(r"(?:(20\d\d)[-./年])?(\d{1,2})[-./月](\d{1,2})日?", line)
    if m and len(line) <= 80:
        try:
            day = date(int(m[1] or year), int(m[2]), int(m[3]))
            if not m[1] and day > date.today() + timedelta(days=30):
                day = day.replace(year=day.year - 1)       # a December report read in January
            state["date"] = day
            found = True
        except ValueError:
            pass
    for rx, item, sheet in ITEMS:
        if re.search(rx, low):
            transport, origin = ITEM_DEFAULTS.get(item, ("", ""))
            state.update(item=item, sheet=sheet, new="", transport=transport, origin=origin)
            found = True
            break
    if len(line) <= 80:
        if re.search(r"(?i)\bimport", line):
            state["origin"], state["transport"], found = "", ITEM_DEFAULTS.get(state.get("item"), ("",))[0], True
        if re.search(r"(?i)domestic|国产", line):
            state["transport"], state["origin"], found = "LAND", "", True
        for word, country in COUNTRIES.items():
            if word in low or word in line:
                state["origin"], found = country, True
                if state.get("item") != "CHERRIES":
                    state["transport"] = "OCEAN"
                break
        if re.search(AIR, line):
            state["transport"], found = "AIR", True
        elif re.search(SEA, line):
            state["transport"], found = "OCEAN", True
        if re.search(r"(?i)\bold goods\b|旧货", line):
            state["new"], found = "OLD", True
        elif re.search(r"(?i)\bnew goods\b|新货", line):
            state["new"], found = "", True
    return found


def is_price_line(line):
    """A WeChat offer: it has the team's tabs, or starts with 'seller/volume' or 'volume/'."""
    if "\t" in line and "/" in line:
        return True
    text = normalise(line)
    return bool(re.match(rf"^(?:{NUMBER}\s*[PC件]\s*/|[^/\d][^/]{{0,30}}/\s*{NUMBER}\s*[PC件板])", text, re.I)
                and text.count("/") >= 2)


# ---------------------------------------------------------------- the general part

def box_weight(token, sheet):
    """(kg, n in one) if the token is a box weight: '2.5KG', '2*2.5KG', '3*2KG', '500g', '8*200g',
    '150g*8', '150*6' (grams, said or not). Else None."""
    up = token.upper().replace(" ", "")
    w = re.fullmatch(rf"(\d+)\*({NUMBER})(KG|G)?", up)
    if w and int(w[1]) >= 50 and not w[3]:          # '150*6': 150 g, six of them
        return int(w[1]) / 1000 * float(w[2]), int(float(w[2]))
    if w:
        n, per = int(w[1]), float(w[2])
        per = per / 1000 if w[3] == "G" or (not w[3] and per >= 50) else per
        return n * per, n
    w = re.fullmatch(rf"({NUMBER})(KG|G)?\*(\d+)", up)
    if w and (w[2] or float(w[1]) >= 50):
        per = float(w[1]) / (1000 if w[2] != "KG" else 1)
        return per * int(w[3]), int(w[3])
    w = re.fullmatch(rf"({NUMBER})(KG|G)", up)
    if w:
        return float(w[1]) / (1000 if w[2] == "G" else 1), 1
    return None


def read_general(parts, sheet, item, values):
    """seller/volume/brand/variety/weight/package/... -> values; returns (box, notes)."""
    box = {"weight": None, "in_one": 1, "package": None}
    notes = []
    # seller and volume: 'seller/5P/...', '5P/...' (no seller), 'seller/brand/...' (no volume)
    seller = ""
    if parts and not VOLUME.match(parts[0]):
        if len(parts) > 1 and VOLUME.match(parts[1]):
            seller = parts.pop(0)
        elif re.search(r"[一-鿿]", parts[0]):
            seller = parts.pop(0)
    m = VOLUME.match(parts[0]) if parts else None
    volume = None
    if m:
        parts.pop(0)
        unit = m[2].upper()
        if unit in ("件",):
            notes.append(f"the volume is in boxes ({m[1]}件), not pallets: left empty")
        else:
            volume = float(m[1]) * (20 if unit in ("C", "柜") else 1)        # a container is 20 pallets
            values["_containers"] = unit in ("C", "柜")
        if m[3]:
            parts.insert(0, m[3])                  # '5PC&L': the next part was glued to the volume
    else:
        notes.append("no volume (5P, 1C) in the line")
    values["SELLER"] = seller
    values["VOLUME"] = volume

    words = []
    for p in parts:
        p = p.strip()
        up = p.upper().replace(" ", "")
        if not p:
            continue
        w = box_weight(p, sheet)
        if w:
            box["weight"], box["in_one"] = w[0], max(box["in_one"], w[1])
            continue
        n_in_one = re.fullmatch(r"(\d)IN1(?:BOX)?", up)
        if n_in_one:
            box["in_one"] = int(n_in_one[1])
            continue
        if up in ("CARTON", "PLASTIC", "WOODEN", "纸箱", "胶箱", "胶框", "木箱"):
            box["package"] = {"纸箱": "CARTON", "胶箱": "PLASTIC", "胶框": "PLASTIC", "木箱": "WOODEN"}.get(up, up)
            continue
        if p in PROVINCES:
            values["ORIGIN"] = PROVINCES[p]
            continue
        if sheet in ("APPLES", "GRAPES", "PEARS") and re.fullmatch(r"\d{3}", up):
            values["GROWER"] = int(up)                 # '039', '801': the grower number
            continue
        if re.fullmatch(r"PG|HG|XF|XFANCY|EXTRAFANCY|PREMIUM|CLASS\d|CAT\d", up):
            values["CLASS"] = p.upper()
            continue
        words.append(p)

    # brand / variety (and exporter): 'GARCES/ROYAL RAINIER', 'AQU ANQA/PRIZE/SEKOYA POP', 'FRESH CHERRY(C&L)'
    exporter = ""
    if len(words) >= 3:
        exporter, words = words[0], words[1:]
    brand = words[0] if words else ""
    variety = " ".join(words[1:]) if len(words) > 1 else ""
    m = re.match(r"^(.*?)\(([^)]+)\)$", brand)
    if m and m[2].strip() in ("胶框", "胶箱", "纸箱", "木箱"):          # 'UNIFRUTTI（胶框）': the box, not the exporter
        brand = m[1].strip()
        box["package"] = {"纸箱": "CARTON", "木箱": "WOODEN"}.get(m[2].strip(), "PLASTIC")
    elif m and not exporter and re.search(r"[A-Za-z]", m[2]) and m[1].strip():
        brand, exporter = m[1].strip(), m[2].strip()
    if brand and not variety:                    # 'FORTUNESWEET ARYANA': a known variety at the end of the brand
        for v in sorted(VARIETIES.get(sheet, []), key=len, reverse=True):
            if brand.upper().endswith(v) and len(brand) > len(v):
                brand, variety = brand[:-len(v)].strip(), brand[-len(v):]
                break
    values.update(EXPORTER=exporter, BRAND=brand, VARIETY=variety)
    return box, notes


# ---------------------------------------------------------------- the sizes and prices part

def _size_rx(sheet):
    return SIZES.get(sheet, SIZES["_"])


def prices_start(parts, sheet):
    """Where the sizes and prices start among a line's '/' parts (for a line without its tabs), or None."""
    rx = re.compile(rf"^(?:{_size_rx(sheet)}|{MIX})\s*(?:[#/+]?\s*{RANGE})?[一-鿿]*$", re.I)
    for i, p in enumerate(parts):
        first = re.split(r"[,\s]", p.strip())[0].upper()
        if i >= 1 and first and rx.match(first) and not re.fullmatch(r"\d?IN1|\d+(?:\.\d+)?(?:KG|G)", first):
            return i
    return None


def read_prices(text, sheet):
    """'56#64#60开', 'J/2000,2J/2500-2600', '36/40/100 44/48/90', '18+/60', '统价50' ->
    (groups [{weight, in_one, prices {size: price}}], comment pieces, problems)."""
    size_rx = _size_rx(sheet)
    t = normalise(text).upper()
    t = re.sub(NOISE, "", t)
    t = re.sub(r"(?<=[A-Z])\.?#", "", t) if sheet in ("CHERRIES", "GRAPES") else t     # 'JD#380', 'XLD.#170'
    t = re.sub(r"(\d{1,3})#(?=\d{1,3}#)", r"\1#/", t)                                  # '20#22#120'
    t = re.sub(rf"({size_rx})-({size_rx})(?=/)", r"\1/\2", t)                           # '2JD-3JD/50'
    t = re.sub(r"(\d)\s*-\s+(?=\d?[JXL])", r"\1/", t)                                   # 'JD/460- 2JD/560'
    t = re.sub(rf"\b({MIX})\s*/?\s*", "MIX ", t)                                        # '统价50', 'MIX/50'
    element = re.compile(rf"^(?P<size>MIX|{size_rx})?\s*(?P<price>{RANGE})?(?P<tail>.*)$")
    numberish = re.compile(rf"^(?:{size_rx}|{RANGE})")

    groups = [{"weight": None, "in_one": 1, "prices": {}}]
    comment, problems, pending = [], [], []

    def give(price_text):
        nonlocal pending
        bits = [float(x) for x in re.findall(NUMBER, price_text)]
        price = min(bits)                                 # a range is written as its lower price
        price = int(price) if price.is_integer() else price
        # cherries: the size just before the price ('2J/2JD/270' -> 2JD); the others: every size listed
        for s in (pending[-1:] if sheet == "CHERRIES" else pending) or ["MIX"]:
            groups[-1]["prices"][s] = price
        pending = []

    for group in (g for g in re.split(r"[,;\s]+", t) if g):
        elements = [e for e in group.split("/")]
        for i, e in enumerate(elements):
            e = e.strip()
            if not e:
                continue
            w = box_weight(e, sheet)
            if w:                                         # a second weight: another row ('4KG ... /10KG ...')
                if groups[-1]["prices"]:
                    groups.append({"weight": None, "in_one": 1, "prices": {}})
                groups[-1]["weight"], groups[-1]["in_one"] = w
                continue
            if re.fullmatch(r"\dIN1", e):
                groups[-1]["in_one"] = int(e[0])
                continue
            m = element.match(e)
            size, price, tail = m["size"], m["price"], m["tail"].strip()
            if size and not price and tail:               # 'MOVE', 'LEFT': words, not a size
                size = None
                price, tail = None, e
            if not size and price and tail and not pending:
                comment.append(e)                         # '17P', '0.5C': how it sold
                continue
            if size:
                pending.append(size.rstrip("#+"))
            if price:
                later = [x for x in elements[i + 1:] if x.strip()]
                if (not size and sheet not in ("CHERRIES", "BLUEBERRY", "GRAPES") and later
                        and numberish.match(later[0].strip()) and not tail and "-" not in price):
                    pending.append(price)                 # '36/40/100': plain numbers before the price are sizes
                    continue
                give(price)
            elif not size:
                tail = e
            tail = re.sub(r"^开(?!价)|开$", "", tail).strip()
            tail = re.sub(r"^拆[,]?", "", tail).strip()
            if tail:
                comment.append(tail)
    groups = [g for g in groups if g["prices"]]
    return groups, comment, problems


# ---------------------------------------------------------------- one WeChat line

def parse_line(line, state):
    """One WeChat line -> ([Row], [what to check]). No rows: the list says why."""
    sheet, item = state.get("sheet"), state.get("item")
    if not sheet:
        return [], ["no product heading above it (cherries, blueberries, oranges...)"]
    segments = [s.strip() for s in normalise(line).split("\t") if s.strip()]
    checks = []

    # the team's layout: general TAB sizes and prices TAB comment. Without the tabs, find where prices start.
    general, prices, comment = segments[0], (segments[1] if len(segments) > 1 else ""), " ".join(segments[2:])
    parts = [p.strip() for p in general.split("/")]
    start = prices_start(parts, sheet)
    if not prices or not read_prices(prices, sheet)[0]:
        if start is None:
            if len(segments) > 1:
                return [], ["no sizes and prices after the first tab"]
            return [], ["no tabs, and the sizes and prices can't be told apart from the rest: add the tabs "
                        "(general ⇥ sizes and prices ⇥ comment)"]
        # 'seller/.../18+110 ⇥走8P' (first tab missing) or no tabs at all: split where the prices start
        comment = " ".join(x for x in (prices, comment) if x)
        prices = "/".join(parts[start:])
        parts = parts[:start]
        checks.append("no tab before the prices: split by guessing, check the row" if len(segments) > 1
                      else "no tabs in this line: split by guessing, check the row")
    elif start is not None and start < len(parts) - 1:
        checks.append("prices before the first tab too: check the row")

    values = {"DATE": state.get("date"), "REGION": state.get("region"), "ITEM": item,
              "ORIGIN": state.get("origin") or "", "NEW": state.get("new", "")}
    box, notes = read_general(parts, sheet, item, values)
    checks += notes
    groups, words, problems = read_prices(prices, sheet)
    checks += problems
    if not groups:
        return [], ["no price in it"]
    containers = values.pop("_containers", False)
    # containers come by sea; pallets, unless the heading says otherwise, by air (tutorial)
    values["TRANSPORT"] = "OCEAN" if containers else (state.get("transport") or "AIR")
    if item == "BLUEBERRIES" and not containers and (values.get("ORIGIN") in PROVINCES.values()
                                                     or re.search(r"[一-鿿]", values.get("BRAND", ""))):
        values["TRANSPORT"] = "LAND"                  # Yunnan, Sichuan...: Chinese blueberries come by road
    if item == "BLUEBERRIES" and values["TRANSPORT"] != "LAND" and not values.get("ORIGIN"):
        values["ORIGIN"] = "PERU"                     # imported blueberries with no country: Peru
    values["SOLD VOLUME"] = "，".join(x.strip(" /,，") for x in words + [comment] if x.strip(" /,，"))
    if re.search(r"[一-鿿]", values["SOLD VOLUME"]):
        values["SOLD VOLUME"] = values["SOLD VOLUME"].replace(",", "，")      # Chinese text: Chinese commas
    volume = values.pop("VOLUME")
    if volume is not None:
        share = volume / len(groups)                  # one container, two weights: 10 pallets each
        values["VOLUME"] = int(share) if share.is_integer() else round(share, 2)
    if len(groups) > 1:
        checks.append(f"split into {len(groups)} rows (one per weight), the volume shared between them")

    rows, headings = [], SHEETS[sheet]
    for g in groups:
        weight = g["weight"] if g["weight"] is not None else box["weight"]
        in_one = max(g["in_one"], box["in_one"])
        red = set()
        if weight is None and in_one == 2 and item == "CHERRIES":
            weight = 5                                # '2IN1' alone: two 2.5 kg boxes
        if weight is None:
            weight = DEFAULT_WEIGHT.get(item)
            if weight is None and item in MUST_HAVE_WEIGHT:
                red.add("WEIGHT")
        if values.get("VOLUME") is None:
            red.add("VOLUME")
        v = dict(values)
        v["WEIGHT"] = (int(weight) if weight is not None and float(weight).is_integer() else
                       (round(weight, 3) if weight is not None else None))
        if sheet == "CHERRIES":
            v["PACKAGE"] = "CARTON 2 IN 1" if in_one == 2 else (box["package"] or DEFAULT_PACKAGE["CHERRIES"])
        elif item == "AVOCADOS":
            v["PACKAGE"] = box["package"] or (("PLASTIC" if weight >= 10 else "CARTON") if weight else None)
        else:
            v["PACKAGE"] = box["package"] or DEFAULT_PACKAGE.get(item)
        row = Row(sheet, line=line.replace("\t", " ⇥ "))
        for name, value in v.items():
            h = column(headings, name)
            if h and value not in (None, ""):
                row.values[h] = value
        for name in red:
            h = column(headings, name)
            if h:
                row.red.add(h)
        prices = {s: p for s, p in g["prices"].items() if not (s == "MIX" and sheet in DROP_MIX)}
        if not prices:
            continue                                  # only an 'all sizes' price, which this sheet doesn't keep
        for s, price in prices.items():
            h = size_column(headings, s, sheet)
            if h:
                row.values[h] = price
            else:
                what = "the price for every size" if s == "MIX" else f"size {s}"
                msg = f"no column for {what} ({price}) in {sheet}: write it by hand"
                if msg not in checks:
                    checks.append(msg)
        rows.append(row)
    if not rows:
        return [], None                               # nothing this sheet keeps: left out on purpose
    return rows, checks


# ---------------------------------------------------------------- columns

FIRST_COLUMNS = {"DATE": "DATE", "REGION": "REGION", "ITEM": "ITEM", "TRANSPORT": "TRANS", "ORIGIN": "ORIGIN",
                 "EXPORTER": "EX", "BRAND": "BRAND", "VARIETY": "VARIETY", "VOLUME": "VOLUME",
                 "SOLD VOLUME": "SOLD", "WEIGHT": "WEI", "PACKAGE": "PACKAGE", "SELLER": "SELLER", "NEW": "NEW",
                 "GROWER": "GROWER", "CLASS": "CLASS"}


def column(headings, name):
    """The sheet's heading for one of our fields (their spelling varies: 'TRANSORT', 'WEIHT/NO', 'EXORTER')."""
    start = FIRST_COLUMNS[name]
    for h in headings:
        key = h.strip().upper()
        if key.startswith(start) and not (name == "VOLUME" and key.startswith("SOLD")):
            return h
    return None


CHERRY_ROWS = {"10": "XLD", "9.5": "JD", "9": "2JD", "8.5": "3JD", "8": "4JD", "10.5": "LD", "7.5": "5JD", "7": "6JD"}
# sizes the team writes under another column's name
SIZE_ALIASES = {"GRAPES": {"2J": "SJ", "JJ": "SJ"},
                "STONEFRUIT": {"2J": "JJ", "3J": "P"},
                "CITRUS": {"1X": "X", "1XX": "2X"}}
DROP_MIX = {"STONEFRUIT"}                    # 'all sizes' prices aren't typed on these sheets


def size_column(headings, size, sheet):
    """The heading of a size's column on a sheet, or None."""
    size = size.upper().strip()
    size = SIZE_ALIASES.get(sheet, {}).get(size, size)
    if sheet == "CHERRIES" and (m := re.fullmatch(r"(\d?J)L?", size)):
        # the L of '2JL' is 'light' (as the D is 'dark'): it goes in the 2J column; 4J only has a 4JL column
        for want in (m[1], m[1] + "L"):
            for h in headings:
                if h.strip().upper().split(" ")[0] == want:
                    return h
    if size == "MIX":
        for h in headings:
            if h.strip().upper().replace(" ", "") in ("N/S", "NS", "S/N", "MIX"):
                return h
        return None
    if sheet == "CHERRIES":
        m = re.fullmatch(r"(\d+(?:\.\d+)?)D", size)          # '9.5D' = 9.5 row = JD
        want = CHERRY_ROWS.get(m[1], size) if m else {"XL": "XLD"}.get(size, size)
        for h in headings:
            if h.strip().upper().split(" ")[0].split("(")[0] == want:
                return h
        return None
    if sheet == "BLUEBERRY":
        for h in headings:                                   # '18' -> '18+ (JJ)', '22' -> '22', '20' -> '20+'
            if re.fullmatch(rf"{re.escape(size)}\+?(?: \(.*\))?", h.strip()):
                return h
        return None
    for h in headings:          # '56' -> '56#', '32' -> '32(XL)', '4J' -> '4J', '1' -> '1', 'L' -> 'L (28)'
        key = h.strip().upper().replace(" ", "")
        if re.fullmatch(rf"#?{re.escape(size)}#?(?:\(.*\))?", key):
            return h
    return None


# ---------------------------------------------------------------- the whole file

def extract(path, year=None):
    year = year or date.today().year
    report, state = Report(), {}
    for raw in read_docx(path):
        line = raw.strip()
        if not line.strip():
            continue
        if is_price_line(line):
            rows, checks = parse_line(line, state)
            shown = line.replace("\t", " ⇥ ")
            if checks is None:
                continue                              # e.g. an 'all sizes' stone fruit price: not typed
            if not rows:
                report.unread.append((shown, "; ".join(checks)))
                continue
            kept = 0
            for row in rows:
                if not state.get("date") or not state.get("region"):
                    row.red |= {h for h in (column(SHEETS[row.sheet], "DATE"), column(SHEETS[row.sheet], "REGION"))
                                if h and h not in row.values}
                if any(r.sheet == row.sheet and r.values == row.values for r in report.rows):
                    continue                     # exactly the same row again: keep one
                report.rows.append(row)
                kept += 1
            if not kept:
                report.notes.append((shown, "the same row is already there: kept once"))
            elif checks:
                report.notes.append((shown, "; ".join(checks)))
        else:
            read_heading(normalise(line), state, year)
    return report


def extract_files(paths, year=None):
    """Several Word files -> one Report (rows in the order of the files)."""
    total = Report()
    for path in paths:
        r = extract(path, year)
        total.rows += r.rows
        total.unread += r.unread
        total.notes += r.notes
    return total


RED = "F4B6B6"


def write(report, folder):
    """An Excel with a tab per China sheet that has rows (same columns as the final file, to paste the rows
    straight in) and a CHECK tab with the lines to look at. Returns its path."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    from .output import save_workbook

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    book.remove(book.active)
    red = PatternFill("solid", fgColor=RED)
    for sheet, headings in SHEETS.items():
        rows = [r for r in report.rows if r.sheet == sheet]
        if not rows:
            continue
        ws = book.create_sheet(sheet)
        ws.append(headings)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([row.values.get(h) for h in headings])
            for i, h in enumerate(headings, 1):
                cell = ws.cell(ws.max_row, i)
                if isinstance(cell.value, date):
                    cell.number_format = "DD/MM/YYYY"
                if h in row.red:
                    cell.fill = red
        for i, h in enumerate(headings, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = 14 if i <= 20 else 9
        ws.freeze_panes = "A2"
    if report.unread or report.notes:
        ws = book.create_sheet("CHECK")
        ws.append(["Line", "What to check"])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for line, why in report.unread:
            ws.append([line, f"Not read: {why}"])
        for line, why in report.notes:
            ws.append([line, why])
        ws.column_dimensions["A"].width = 90
        ws.column_dimensions["B"].width = 60
    if not book.worksheets:
        book.create_sheet("CHECK").append(["No prices found"])
    days = sorted({r.values[h] for r in report.rows for h in r.values if isinstance(r.values[h], date)})
    day = (days[-1] if days else date.today()).strftime("%d-%m-%Y")
    return save_workbook(book, folder / f"China prices {day}.xlsx")

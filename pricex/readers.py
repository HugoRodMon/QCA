"""Turn any price file (pdf, txt, mhtml/html, xlsx) into something parsers can read."""
import email
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from pathlib import Path


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    size: float = 0
    bold: bool = False
    red: bool = False           # printed in red (some suppliers mark prices that aren't final that way)

    @property
    def xc(self):
        return (self.x0 + self.x1) / 2


@dataclass
class Line:
    words: list
    page: int = 0

    @property
    def text(self):
        return " ".join(w.text for w in self.words)

    @property
    def top(self):
        return min(w.top for w in self.words)

    @property
    def size(self):
        return max(w.size for w in self.words)

    def between(self, x_from, x_to):
        """Text of the words whose centre lies between two x positions."""
        return " ".join(w.text for w in self.words if x_from <= w.xc < x_to)

    def __repr__(self):
        return f"Line({self.text!r})"


@dataclass
class Document:
    path: Path
    kind: str                       # pdf | txt | html | xlsx
    text: str = ""
    lines: list = field(default_factory=list)   # pdf and pictures
    second: list = field(default_factory=list)  # pictures: a second OCR reading, to double-check numbers
    html: str = ""                  # mhtml/html only
    sheets: dict = field(default_factory=dict)  # xlsx only: name -> list of rows (lists of values)

    @property
    def name(self):
        return self.path.name


def load(path):
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        lines = pdf_lines(path)
        return Document(path, "pdf", text="\n".join(l.text for l in lines), lines=lines)
    if ext in IMAGE_TYPES:
        lines, second = ocr_lines(path)
        text = "\n".join(l.text for l in lines + second)
        return Document(path, "image", text=text, lines=lines, second=second)
    if ext in (".mhtml", ".mht", ".html", ".htm"):
        html = read_html(path)
        return Document(path, "html", text=re.sub(r"<[^>]+>", " ", html), html=html)
    if ext in (".xlsx", ".xlsm"):
        sheets = read_xlsx(path)
        text = "\n".join(" ".join(str(v) for v in row if v is not None) for rows in sheets.values() for row in rows)
        return Document(path, "xlsx", text=text, sheets=sheets)
    if ext in (".txt", ".text", ""):
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return Document(path, "txt", text=raw.decode(enc))
            except UnicodeDecodeError:
                continue
    raise ValueError(f"Unsupported file type: {path.name}")


# ---------------------------------------------------------------- pdf

def pdf_lines(path, y_tol=1.6):
    """Every text line of the pdf, with word positions.

    Some suppliers' pdfs have hidden text printed on top of the real text (e.g. a section
    title under the first product). Words are only joined into one line when they share
    the same height on the page *and* a similar font size, which keeps those apart."""
    import pdfplumber

    out = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages):
            raw = page.extract_words(x_tolerance=1.5, y_tolerance=1, keep_blank_chars=False,
                                     use_text_flow=False, extra_attrs=["size", "fontname", "non_stroking_color"])
            # some pdfs have no mapping for the euro glyph (or ™) and give U+FFFD instead
            words = [Word(fix_glyphs(w["text"]), w["x0"], w["x1"], w["top"], round(w["size"], 1),
                          "bold" in w["fontname"].lower(), is_red(w.get("non_stroking_color"))) for w in raw]
            words.sort(key=lambda w: (w.top, w.x0))
            lines = []
            for w in words:
                for line in reversed(lines[-4:]):
                    dt = abs(line.words[0].top - w.top)
                    same_size = abs(line.words[0].size - w.size) <= 0.4
                    if dt <= 0.6 or (dt <= y_tol and same_size):
                        line.words.append(w)
                        break
                else:
                    lines.append(Line([w], pno))
            for line in lines:
                line.words.sort(key=lambda w: w.x0)
            lines.sort(key=lambda l: l.top)
            out.extend(lines)
    return out


def is_red(colour):
    """True for red text: RGB (1, 0, 0)-like or CMYK (0, 1, 1, 0)-like."""
    try:
        c = [float(x) for x in colour]
    except (TypeError, ValueError):
        return False
    if len(c) == 3:
        return c[0] > 0.6 and c[1] < 0.35 and c[2] < 0.35
    if len(c) == 4:
        return c[1] > 0.6 and c[2] > 0.6 and c[0] < 0.3 and c[3] < 0.4
    return False


def red_prices(doc):
    """How many price-like words the pdf prints in red, and whether it has a red note about prices."""
    words = [w for line in getattr(doc, "lines", []) or [] for w in line.words if getattr(w, "red", False)]
    # a price: 9,50 or € 9.50 (not a date like 02.11)
    prices = sum(1 for w in words if re.fullmatch(r"€\s*\d+[.,]\d{2}|\d+,\d{2}", w.text))
    note = " ".join(w.text for w in words if not re.search(r"\d", w.text) and w.text.lower() not in ("exp", "eta", "€"))
    return prices, bool(re.search(r"(?i)\bprices?\b", note))


def fix_glyphs(text):
    """A lone unknown glyph before a price is the € sign; anywhere else (Salute™) it's dropped."""
    if text == "�":
        return "€"
    if re.fullmatch(r"�\d[\d.,]*", text):
        return "€ " + text[1:]
    # drop unknown / private-use glyphs (trademark signs and the like)
    return "".join(ch for ch in text if ch not in "�™®©"
                   and unicodedata.category(ch) not in ("Co", "Cc", "Cn"))


# ---------------------------------------------------------------- images (OCR)

IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif")


def ocr_lines(path):
    """Text of a picture (see ocr.py) as lines of words with positions, like pdf_lines, so the same
    supplier parsers work on pictures. Returns (main lines, second reading's lines)."""
    from .ocr import read_picture

    main, second = read_picture(path)
    as_lines = lambda ws: _rows([Word(t, x0, x1, top, round(h, 1)) for t, x0, x1, top, h in ws])  # noqa: E731
    return as_lines(main), as_lines(second)


def _rows(words):
    """Group words into table rows by their height on the page (OCR splits a row into pieces)."""
    words.sort(key=lambda w: (w.top + w.size / 2, w.x0))
    lines = []
    for w in words:
        mid = w.top + w.size / 2
        line = lines[-1] if lines else None
        if line and abs(mid - line.mid) <= max(2.5, 0.45 * w.size):
            line.words.append(w)
            line.mid = sum(x.top + x.size / 2 for x in line.words) / len(line.words)
        else:
            line = Line([w])
            line.mid = mid
            lines.append(line)
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    return lines


# ---------------------------------------------------------------- html / mhtml

def read_html(path):
    if path.suffix.lower() in (".mhtml", ".mht"):
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=policy.default)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                # the part's charset, else the page's own <meta charset> (Schrijvershof: UTF-8 'Brazilië'), else UTF-8
                raw = part.get_payload(decode=True) or b""
                m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:5000], re.I)
                charset = part.get_content_charset() or (m[1].decode() if m else "utf-8")
                try:
                    return raw.decode(charset, errors="replace")
                except LookupError:
                    return raw.decode("utf-8", errors="replace")
        raise ValueError(f"No HTML found in {path.name}")
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- xlsx

def read_xlsx(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb}


# ---------------------------------------------------------------- dates

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTHS.update({"okt": 10, "mei": 5, "mrt": 3, "ene": 1, "abr": 4, "ago": 8, "dic": 12})


def find_date(doc):
    """Date of the price list: from the file name first (DD-MM-YYYY), then from the content."""
    m = re.search(r"(\d{1,2})[-_.](\d{1,2})[-_.](\d{4})", doc.name)
    if m:
        return datetime(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r"(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})", doc.name)     # 'WhatsApp Image 2026-10-29 ...'
    if m:
        return datetime(int(m[1]), int(m[2]), int(m[3]))
    text = doc.text[:3000]
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", text)
    if m:
        return datetime(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s-]+(?:of\s+)?([a-z]{3})[a-z]*[\s-]+(\d{2,4})", text, re.I)
    if m and m[2].lower() in MONTHS:
        y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        return datetime(y, MONTHS[m[2].lower()], int(m[1]))
    return None

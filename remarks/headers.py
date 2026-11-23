"""Column names the website writes as pictures (rotated text) -> their names.

Tried in order: the picture's alt/title text, words in its address (…?text=Bruises, …/bruises.png), then the
picture itself read with OCR, turned both ways (the text runs bottom to top). What's read is snapped to the
names the website uses (report.KNOWN_COLUMNS) when it's close to one.
"""
import base64
import difflib
import io
import re
import urllib.parse
import urllib.request

from .report import KNOWN_COLUMNS, snap

_cache = {}          # picture address -> name (or None), for the whole session
_ocr = None


def name_of(cell):
    """The column name a header cell's pictures say, or None."""
    for img in cell.get("img") or []:
        for text in (img.get("alt"), img.get("title")):
            name = _usable(text)
            if name:
                return name
        src = img.get("src") or ""
        if src in _cache:
            if _cache[src]:
                return _cache[src]
            continue
        name = _from_address(src) or _from_picture(src)
        _cache[src] = name
        if name:
            return name
    return None


def _usable(text):
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t or t.lower() in ("image", "img", "icon", "header", "picture"):
        return None
    return snap(t) or closest(t) or t


def _from_address(src):
    if not src or src.startswith("data:"):
        return None
    parts = urllib.parse.urlsplit(src)
    for _, v in urllib.parse.parse_qsl(parts.query):
        name = snap(v) or closest(v)
        if name:
            return name
    stem = urllib.parse.unquote(parts.path.rsplit("/", 1)[-1]).rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    return snap(stem) or closest(stem, 0.9)


def _from_picture(src):
    data = _picture_bytes(src)
    if not data:
        return None
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None
    best = None
    for angle in (-90, 90, 0):                                 # bottom-to-top text first
        text, score = _read(img.rotate(angle, expand=True))
        if text:
            name = snap(text) or closest(text)
            if name:
                return name
            if not best or score > best[1]:
                best = (text, score)
    return best[0] if best and best[1] > 0.8 else None


def _picture_bytes(src):
    if src.startswith("data:"):
        try:
            return base64.b64decode(src.split(",", 1)[1])
        except Exception:
            return None
    if not src.lower().startswith(("http://", "https://")):
        return None
    try:
        request = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=6) as r:
            return r.read(2_000_000)
    except Exception:
        return None                                              # behind the website's login: named by hand


def _read(img):
    """(text, confidence) read from a picture."""
    global _ocr
    try:
        import numpy as np
        if _ocr is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        # small header pictures read better bigger, dark text on white
        from PIL import ImageOps
        if img.height < 64:
            img = img.resize((img.width * 64 // max(img.height, 1), 64))
        gray = ImageOps.grayscale(img)
        if sum(gray.getdata()) / (gray.width * gray.height) < 128:
            gray = ImageOps.invert(gray)                         # white text on the grey header
        result, _ = _ocr(np.array(gray.convert("RGB")))
    except Exception:
        return "", 0.0
    if not result:
        return "", 0.0
    text = " ".join(r[1] for r in result)
    score = sum(float(r[2]) for r in result) / len(result)
    return text.strip(), score


def closest(text, cutoff=0.8):
    """The known column name closest to a misread one ('Bruiscs' -> 'Bruises'), or None."""
    t = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not t:
        return None
    names = {n.lower(): n for n in KNOWN_COLUMNS}
    match = difflib.get_close_matches(t, list(names), n=1, cutoff=cutoff)
    return names[match[0]] if match else None

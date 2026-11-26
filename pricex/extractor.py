"""Find out which supplier a file is from, and extract its prices.

The file name is NOT trusted: files arrive as 'WhatsApp Image ...jpeg', with typos ('Westaflia'),
or even named after the wrong supplier. The content decides:
  1. identifiers in the text (web domain, e-mail, company name, Chamber of Commerce number...):
     each supplier's `match_text`. If found, the supplier is certain.
  2. otherwise the layout: every supplier that reads this kind of file tries it, and the one that
     reads the most real products wins (`layout_hints` in each supplier add to its score).
  3. the file name only helps to choose between equally good candidates, and typos are tolerated.
If the name and the content disagree, the content wins and the report says so.
"""
import copy
import difflib
import re
import traceback
from pathlib import Path

from . import readers
from .base import suppliers
from .model import Result


def name_hint(path):
    """Supplier the file name suggests (typos tolerated: 'Westaflia' -> Westfalia), or None."""
    words = re.findall(r"[a-z]{3,}", Path(path).stem.lower().replace(".", " "))
    best, best_score = None, 0.0
    for s in suppliers():
        keys = set(s.match_names) | {s.name.lower()}
        for k in keys:
            # long keys anywhere in the name; short ones ('edn') only as a whole word ('wednesday' isn't EDN)
            if (len(k) >= 5 and k in Path(path).name.lower()) or k in words:
                return s
            for key_word in re.findall(r"[a-z]{4,}", k):
                for w in words:
                    score = difflib.SequenceMatcher(None, w, key_word).ratio()
                    if score > best_score:
                        best, best_score = s, score
    return best if best_score >= 0.8 else None


def identify(path, doc=None):
    """(supplier, how it was recognised, warning or ''). Without the content, only the name is used."""
    path = Path(path)
    hint = name_hint(path)
    if doc is None or getattr(hint, "name_wins", False):
        return hint, "file name", ""
    ext = path.suffix.lower()
    candidates = [s for s in suppliers() if ext in s.file_types]
    text = doc.text.lower()

    # 1. identifiers in the content
    found = {s: [k for k in s.match_text if k in text] for s in candidates}
    found = {s: k for s, k in found.items() if k}
    if found:
        best = max(found, key=lambda s: len(found[s]))
        if sum(len(k) == len(found[best]) for k in found.values()) == 1:
            return best, f"content ('{found[best][0]}')", _conflict(hint, best)
        candidates = [s for s in found if len(found[s]) == len(found[best])]

    # 2. layout: let each candidate read the file
    scores = []
    for s in candidates:
        hints = sum(1 for rx in s.layout_hints if re.search(rx, text, re.I | re.M))
        if not hints:
            continue            # reading products isn't enough (flexible parsers read anyone's list):
                                # the file must also look like this supplier's layout
        rows = _trial(s, doc)
        scores.append((rows + 15 * hints, rows, s))
    scores.sort(key=lambda x: -x[0])
    if scores and scores[0][1] > 0:
        top = [x for x in scores if x[0] >= 0.75 * scores[0][0]]
        if len(top) == 1:
            return top[0][2], "layout", _conflict(hint, top[0][2])
        if hint in [x[2] for x in top]:
            return hint, "layout + file name", ""
        names = ", ".join(x[2].name for x in top)
        return None, "", f"could be {names}: rename the file with the supplier's name"
    # 3. nothing in the content: the name is all there is
    if hint and ext in hint.file_types:
        return hint, "file name only", "nothing in the content confirms the supplier"
    return None, "", ""


def _trial(supplier, doc):
    """How many real products the supplier's parser reads from the file (0 if it fails)."""
    try:
        rows = supplier.parse(copy.copy(doc))
        return len(supplier.finalize(rows, Result(supplier.name, "", None)))
    except Exception:
        return 0


def _conflict(hint, chosen):
    if hint and hint is not chosen:
        return f"the file name says {hint.name}, but the content is {chosen.name}'s: used {chosen.name}"
    return ""


def extract_file(path, supplier=None):
    """Returns (Result or None, error message or None)."""
    path = Path(path)
    finals = {s.final_file.lower(): s.name for s in suppliers() if s.final_file}
    if path.name.lower() in finals:
        return None, f"{path.name}: this is the final Excel of {finals[path.name.lower()]}, not a price list"
    try:
        doc = readers.load(path)
    except Exception as e:
        return None, f"{path.name}: could not read the file ({e})"
    how, note = "chosen", ""
    if supplier is None:
        supplier, how, note = identify(path, doc)
    if supplier is None:
        return None, f"{path.name}: not a price list of a known supplier" + (f" ({note})" if note else "")
    date = readers.find_date(doc)
    result = Result(supplier.name, path.name, date)
    result.identified_by = how
    if note:
        result.warnings.append(note)
    if date is None:
        result.warnings.append("no date found in the file name or content")
    if doc.kind == "image":
        result.warnings.append("read from a picture (OCR): compare the rows with the picture before using them; "
                               "red cells are rows with missing or unclear data")
    red, red_note = readers.red_prices(doc)
    if red:
        result.warnings.append(
            f"{red} price{'s are' if red > 1 else ' is'} printed in red{' (with a red note about prices)' if red_note else ''}: "
            + ("not final, left out of the Excel (listed in the price checks)" if supplier.drop_not_final else
               "they may not be final; marked red in the Excel where the supplier's reader knows them"))
    try:
        rows = supplier.parse(doc)
    except Exception:
        return None, f"{path.name} ({supplier.name}): the parser failed. The layout may have changed.\n{traceback.format_exc(limit=3)}"
    result.rows = supplier.finalize(rows, result)
    if not result.rows:
        result.warnings.append("no prices found (everything on request, or the layout changed)")
    return result, None

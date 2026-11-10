"""Write the extracted prices to Excel, using each supplier's column layout."""
import difflib
import re
from collections import OrderedDict, defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from . import normalize as N
from . import templates
from .model import DEFAULT_COLUMNS, FIELDS

BASE = {"DATE", "SPECIE", "VARIETY", "ORIGIN", "BRAND", "WEIGHT (KG)", "PACKAGING", "BOX PP",
        "CAT", "DETAIL", "TYPE", "SIZE", "PRICE EUR"}
WIDE_DEFAULT = ["DATE", "SPECIE", "VARIETY", "ORIGIN", "BRAND", "WEIGHT (KG)", "PACKAGING",
                "BOX PP", "CAT", "DETAIL"]
NEW = PatternFill("solid", fgColor="FFF2A8")
SUSPECT = PatternFill("solid", fgColor="F4B6B6")
BOLD = Font(bold=True)


def value(row, header, date):
    h = header.strip().upper()
    if h == "DATE":
        return date
    attr = FIELDS.get(h)
    v = getattr(row, attr) if attr else None
    return None if v in ("", None) else v


def size_key(x):
    s = str(x).strip().upper().replace("#", "").replace(" ", "").replace("MM", "").replace("*", "")
    s = s.replace("-", "/").replace("–", "/")
    return re.sub(r"\.0$", "", s)


def safe_title(name):
    return re.sub(r"[\[\]:*?/\\]", "-", name)[:31]


def _finish(ws, n_cols, new_cols=()):
    for c in ws[1]:
        c.font = BOLD
        if c.column in new_cols:
            c.fill = NEW
    for (cell,) in ws.iter_rows(min_row=2, max_col=1):
        cell.number_format = "DD/MM/YYYY"
    for i in range(1, n_cols + 1):
        letter = ws.cell(1, i).column_letter
        ws.column_dimensions[letter].width = 12 if i > 1 else 11
    ws.freeze_panes = "A2"


# ---------------------------------------------------------------- long (one row per size)

def write_long_sheet(wb, supplier, results, tpl):
    headers = next(iter(tpl["sheets"].values())) if tpl else DEFAULT_COLUMNS
    ws = wb.create_sheet(safe_title(supplier.name))
    ws.append(headers)
    n = 0
    price_col = next((i for i, h in enumerate(headers, 1) if h.strip().upper() == "PRICE EUR"), None)
    must_fill = [i for i, h in enumerate(headers, 1) if h.strip().upper() in supplier.must_fill]
    for res in results:
        for r in res.rows:
            values = [value(r, h, res.date) for h in headers]
            ws.append(values)
            n += 1
            if r.flag and price_col:
                ws.cell(ws.max_row, price_col).fill = SUSPECT
            for i in must_fill:                 # missing and needed: red, to be filled in by hand
                if values[i - 1] is None:
                    ws.cell(ws.max_row, i).fill = SUSPECT
    _finish(ws, len(headers))
    return n


# ---------------------------------------------------------------- wide (tab per species, column per size)

def pick_sheet(supplier, species, sheets):
    canon = N.find_species(species) or species
    if canon in supplier.sheet_names:
        return supplier.sheet_names[canon]
    for name in sheets:
        if N.find_species(name) == canon:
            return name
    close = difflib.get_close_matches(canon.lower(), [s.lower() for s in sheets], n=1, cutoff=0.75)
    if close:
        return next(s for s in sheets if s.lower() == close[0])
    upper = sum(s.isupper() for s in sheets) > len(sheets) / 2
    return canon.upper() if upper else canon


def write_wide_file(path, supplier, results, tpl):
    sheets = OrderedDict((k, list(v)) for k, v in (tpl or {}).get("sheets", {}).items())
    groups = defaultdict(list)          # sheet -> [(date, row)]
    for res in results:
        for r in res.rows:
            groups[pick_sheet(supplier, r.specie, sheets)].append((res.date, r))

    wb = Workbook()
    wb.remove(wb.active)
    notes = []
    order = [s for s in sheets if s in groups] + [s for s in groups if s not in sheets]
    for sheet in order:
        headers = sheets.get(sheet)
        if headers is None:
            base_src = next(iter(sheets.values()), WIDE_DEFAULT)
            headers = [h for h in base_src if h.strip().upper() in BASE - {"SIZE", "PRICE EUR"}] or WIDE_DEFAULT
            notes.append(f"new tab '{sheet}' (not in the final file)")
        headers = list(headers)
        base = [h for h in headers if h.strip().upper() in BASE]
        size_cols = {size_key(h): i for i, h in enumerate(headers) if h.strip().upper() not in BASE}
        new_cols = set()

        # one Excel row per product; its sizes go into the size columns
        out_rows = []
        index = {}
        for date, r in groups[sheet]:
            key = (date,) + tuple(str(value(r, h, date)) for h in base if h.strip().upper() != "DATE")
            k = size_key(r.size)
            if k not in size_cols and r.group and size_key(r.group) in size_cols:
                k = size_key(r.group)                 # the final file has a "45/50" column: keep it grouped
            if k not in size_cols:
                label = _size_label(r.size, headers)
                headers.append(label)
                size_cols[k] = len(headers) - 1
                new_cols.add(len(headers))
                notes.append(f"{sheet}: new size column '{label}'")
            target = index.get(key)
            if target is not None and target["prices"].get(k) == r.price:
                continue                              # same grouped price already written
            if target is None or k in target["prices"]:
                target = {"date": date, "row": r, "prices": {}}
                out_rows.append(target)
                index[key] = target
            target["prices"][k] = r.price
            if r.flag:
                target.setdefault("flags", set()).add(k)

        ws = wb.create_sheet(safe_title(sheet))
        ws.append(headers)
        for t in out_rows:
            flagged_cols = {size_cols[k] for k in t.get("flags", ())}
            line = []
            for i, h in enumerate(headers):
                if h.strip().upper() in BASE:
                    line.append(value(t["row"], h, t["date"]))
                else:
                    line.append(next((p for k, p in t["prices"].items() if size_cols[k] == i), None))
            ws.append(line)
            for i in flagged_cols:
                ws.cell(ws.max_row, i + 1).fill = SUSPECT
        _finish(ws, len(headers), new_cols)
    path = save_workbook(wb, path)
    return sum(len(v) for v in groups.values()), notes, path


def _size_label(size, headers):
    sizes = [h for h in headers if h.strip().upper() not in BASE]
    if str(size).upper() == "N/S" or not re.fullmatch(r"\d+", str(size)):
        return str(size)
    if sum(h.endswith("#") for h in sizes) > len(sizes) / 2:
        return f"{size}#"
    if sum(h.startswith("#") for h in sizes) > len(sizes) / 2:
        return f"#{size}"
    return str(size)


# ---------------------------------------------------------------- saving

class OutputFolderError(Exception):
    """The output folder can't be written to at all."""


def folder_problem(folder, error):
    return OutputFolderError(
        f"Windows doesn't allow saving in this folder:\n{folder}\n\n({error})\n\n"
        "Possible causes:\n"
        " - the folder is read-only, or on a shared/network drive without write access\n"
        " - Windows Security 'Controlled folder access' blocks unknown programs from writing in\n"
        "   Documents/Desktop (allow PriceExtractor.exe there, or use another folder)\n"
        " - OneDrive is busy with the folder\n\n"
        "Choose another output folder (e.g. one in Downloads) and try again.")


def save_workbook(wb, path):
    """Save; if the file is open in Excel (Windows locks it), save as 'name (2).xlsx', '(3)'...
    Returns the path actually written."""
    path = Path(path)
    candidates = [path] + [path.with_name(f"{path.stem} ({i}){path.suffix}") for i in range(2, 30)]
    first_error = None
    for p in candidates:
        try:
            wb.save(p)
            return p
        except PermissionError as e:
            first_error = first_error or e
            if not p.exists():
                break           # a new file can't be created either: the folder itself is the problem
    raise folder_problem(path.parent, first_error)


# ---------------------------------------------------------------- all

def is_wide(supplier, tpl):
    """A final file split into a tab per species gets its own file; otherwise a tab in the combined one."""
    if tpl and tpl.get("sheets"):
        return len(tpl["sheets"]) > 1
    return supplier.layout == "wide"



def write_all(results, out_dir, supplier_by_name):
    """Combined workbook for 'long' suppliers, separate files for 'wide' ones.
    Returns (combined path or None, [(supplier, separate path)], notes)."""
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise folder_problem(out_dir, e)
    tpls = templates.load()
    by_supplier = OrderedDict()
    for res in results:
        by_supplier.setdefault(res.supplier, []).append(res)

    dates = sorted({r.date for r in results if r.date})
    label = dates[-1].strftime("%d-%m-%Y") if dates else "undated"

    combined = None
    separate, notes, renamed = [], [], []          # renamed: [(wanted name, name used)] when a file was open
    wb = Workbook()
    wb.remove(wb.active)
    for name, res_list in by_supplier.items():
        sup = supplier_by_name[name]
        if is_wide(sup, tpls.get(name)):
            own = sorted(r.date for r in res_list if r.date)
            wanted = out_dir / f"{name} {own[-1].strftime('%d-%m-%Y') if own else label}.xlsx"
            n, sheet_notes, path = write_wide_file(wanted, sup, res_list, tpls.get(name))
            separate.append((name, path))
            notes += [f"{name}: {x}" for x in sheet_notes]
            if path != wanted:
                renamed.append((wanted.name, path.name))
        else:
            write_long_sheet(wb, sup, res_list, tpls.get(name))
    if wb.sheetnames:
        wanted = out_dir / f"Prices {label}.xlsx"
        combined = save_workbook(wb, wanted)
        if combined != wanted:
            renamed.append((wanted.name, combined.name))
    return combined, separate, notes, renamed

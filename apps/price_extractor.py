"""Price Extractor (Europe): daily supplier price lists -> Excel, in the final files' columns."""
import re
import threading
from pathlib import Path

from pricex.base import suppliers
from pricex.extractor import name_hint
from pricex.output import OutputFolderError
from pricex.pipeline import SUPPORTED, run

from .common import load_settings, remember

KINDS = {".pdf": "PDF", ".txt": "TXT", ".mhtml": "WEB", ".mht": "WEB", ".html": "WEB", ".htm": "WEB",
         ".xlsx": "XLSX", ".xlsm": "XLSX"}
PICTURES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
TAB_NOTES = {
    "checks": "Prices far from the usual offer of the same product. Red cells in the Excel; only “dropped” rows were removed.",
    "unknown": "Products with a price the extractor doesn't know. Add them to pricex/data/species.json and run again.",
    "failed": "Files whose supplier wasn't recognised, or whose layout changed so much the parser failed.",
    "newcols": "Yellow header cells: columns or tabs that don't exist in the final file yet.",
}


def file_kind(path):
    ext = Path(path).suffix.lower()
    return KINDS.get(ext) or ("IMG" if ext in PICTURES else ext[1:5].upper() or "?")


def how_text(result):
    """How a supplier was recognised, in the words of the files table."""
    how = result.identified_by
    if file_kind(result.file) == "IMG":
        return "✓ read from picture (OCR)"
    if how.startswith("content"):
        return "✓ confirmed from content"
    if how.startswith("layout"):
        return "✓ matched by layout"
    return "from the file name only" if how.startswith("file name") else how


def _check_item(supplier, text):
    """One line of Result.corrections as a row of the Price checks tab. None if it isn't about a price."""
    if text.startswith("removed "):                    # "removed 2 identical row(s)": only for the full log
        return None
    dropped = text.startswith("dropped ")
    body = text[len("dropped "):] if dropped else text[len("CHECK "):] if text.startswith("CHECK ") else text
    body = re.sub(r"\s*\(kept, marked red\)$", "", body)
    title, _, detail = body.partition(": ")
    return {"title": title, "supplier": supplier, "detail": detail,
            "tag": "Dropped" if dropped else "Red cell", "kind": "bad" if dropped else "warn"}


def _warning_item(result, text):
    return {"title": text[0].upper() + text[1:], "supplier": f"{result.supplier} · {result.file}", "detail": "",
            "tag": "Warning", "kind": "warn"}


def _skipped_item(supplier, text):
    title, _, rest = text.partition(" (")
    return {"title": title, "supplier": supplier, "detail": rest.rstrip(")"), "tag": "Not extracted", "kind": "warn"}


def _failed_item(text):
    head = text.partition("\n")[0]                     # a parser failure has its traceback after the first line
    name, _, reason = head.partition(": ")
    who = ""
    if name.endswith(")") and " (" in name:            # "file.pdf (Verdi): the parser failed"
        name, _, who = name[:-1].rpartition(" (")
    elif "known supplier" in reason:
        who = "No supplier matched"
    return {"title": name, "supplier": who, "detail": reason, "tag": "Not processed", "kind": "bad"}


def _new_item(text):
    """'Verdi: Plums: new size column '45/50'' or 'Verdi: new tab 'Kiwis' (not in the final file)'"""
    supplier, _, rest = text.partition(": ")
    tab, marker, label = rest.partition(": new size column ")
    if marker:
        return {"title": f"{tab} · size {label.strip(chr(39))}", "supplier": supplier,
                "detail": f"New column in tab {tab}.", "tag": "New column", "kind": "new"}
    tab = re.search(r"new tab '(.*)'", rest)
    return {"title": tab[1] if tab else rest, "supplier": supplier, "detail": "This tab isn't in the final file yet.",
            "tag": "New tab", "kind": "new"}


def _tab_count(path):
    try:
        from openpyxl import load_workbook
        book = load_workbook(path, read_only=True)
        count = len(book.sheetnames)
        book.close()
        return count
    except Exception:
        return 0


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def report_payload(report):
    """Everything the results panel shows, from what the pipeline reports."""
    wide = {name for name, _ in report.separate}
    outputs = []
    if report.combined:
        names = sorted({r.supplier for r in report.results if r.rows and r.supplier not in wide})
        outputs.append({"name": report.combined.name, "path": str(report.combined), "detail": "Combined · " + ", ".join(names)})
    for name, path in report.separate:
        mine = [n for n in report.notes if n.startswith(name + ": ")]
        columns = sum(1 for n in mine if "new size column" in n)
        parts = ["Tab per species", _plural(_tab_count(path), "tab")]
        if len(mine) > columns:
            parts.append(_plural(len(mine) - columns, "new tab"))
        if columns:
            parts.append(_plural(columns, "new column"))
        outputs.append({"name": path.name, "path": str(path), "detail": " · ".join(parts)})

    checks = []
    for r in report.results:
        checks += [item for item in (_check_item(r.supplier, c) for c in r.corrections) if item]
        checks += [_warning_item(r, w) for w in r.warnings]
    unknown = [_skipped_item(r.supplier, s) for r in report.results for s in r.skipped]
    failed = [_failed_item(e) for e in report.errors]
    newcols = [_new_item(n) for n in report.notes]
    return {"rows": sum(len(r.rows) for r in report.results), "outputs": outputs,
            "renamed": [{"wanted": w, "used": u} for w, u in report.renamed],
            "issues": {"checks": checks, "unknown": unknown, "failed": failed, "newcols": newcols},
            "notes": TAB_NOTES, "log": report.text(),
            "to_look_at": len(checks) + len(unknown) + len(newcols), "not_processed": len(failed)}


def error_text(e):
    if isinstance(e, OutputFolderError):
        return str(e)
    if isinstance(e, PermissionError):
        return f"Windows refused access to a file: {e}. If it's one of the price Excel files, close it in Excel and try again."
    return f"Something went wrong: {e}"


class Api:
    def __init__(self, host):
        self._host = host

    def state(self):
        return {"out": load_settings().get("output", str(Path.home() / "Downloads" / "Prices extracted"))}

    def choose(self):
        """The file dialog. Returns the paths chosen."""
        types = "Price files (" + ";".join(f"*{e}" for e in sorted(SUPPORTED)) + ")"
        paths = self._host.ask_files(load_settings().get("input", str(Path.home() / "Downloads")), [types])
        if paths:
            remember("input", str(Path(paths[0]).parent))
        return paths

    def add(self, paths, known):
        """Files and folders -> new rows for the table. A final (OneDrive) Excel is left out: it isn't a price list."""
        finals = {s.final_file.lower() for s in suppliers() if s.final_file}
        known, files, left_out = set(known), [], []
        for p in map(Path, paths):
            for f in sorted(x for x in p.iterdir() if x.suffix.lower() in SUPPORTED) if p.is_dir() else [p]:
                if str(f) in known:
                    continue
                if f.name.lower() in finals:
                    left_out.append(f.name)
                    continue
                known.add(str(f))
                guess = name_hint(f)                      # a first guess; the content decides when extracting
                files.append({"path": str(f), "name": f.name, "kind": file_kind(f), "guess": guess.name if guess else None})
        return {"files": files, "left_out": left_out}

    def choose_out(self, current):
        return self._host.ask_folder(current)

    def open_out(self, folder):
        return self._host.open_folder(folder)

    def open_file(self, path):
        return self._host.open_file(path)

    def start(self, paths, out):
        remember("output", out)
        threading.Thread(target=self._work, args=(paths, Path(out)), daemon=True).start()

    def _work(self, paths, out):
        emit = self._host.emit

        def progress(i, n, name):
            emit("price.progress", {"i": i, "n": n, "name": name})

        def file_done(path, result, error):
            if result:
                emit("price.file", {"path": str(path), "supplier": result.supplier, "how": how_text(result), "rows": len(result.rows)})
            else:
                head = (error or "").partition("\n")[0]
                emit("price.file", {"path": str(path), "failed": True, "reason": head.partition(": ")[2],
                                    "unrecognised": "known supplier" in head})

        try:
            emit("price.done", report_payload(run(paths, out, progress, file_done)))
        except Exception as e:                            # never leave the screen stuck
            emit("price.error", error_text(e))


def run_without_window(args):
    """DQSApps.exe --extract <files or folders> -o <output folder>   (writes report.txt there)"""
    out = Path(args[args.index("-o") + 1]) if "-o" in args else Path.cwd() / "Prices extracted"
    inputs = [Path(a) for a in args if a not in ("--extract", "-o") and Path(a) != out]
    files = []
    for p in inputs:
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in SUPPORTED) if p.is_dir() else [p]
    report = run(files, out)
    out.mkdir(parents=True, exist_ok=True)
    return report, out

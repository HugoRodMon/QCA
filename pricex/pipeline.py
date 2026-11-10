"""Run a batch of files: extract, write the Excel output, and build the end-of-run report."""
from dataclasses import dataclass, field
from pathlib import Path

from .base import suppliers
from .extractor import extract_file
from .output import write_all

SUPPORTED = {".pdf", ".txt", ".mhtml", ".mht", ".html", ".htm", ".xlsx", ".xlsm",
             ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}     # pictures are read with OCR


@dataclass
class Report:
    results: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    combined: object = None
    separate: list = field(default_factory=list)     # [(supplier, path)]
    notes: list = field(default_factory=list)
    renamed: list = field(default_factory=list)      # [(wanted, used)] files saved under another name

    def text(self):
        out = []
        if self.renamed:
            out.append("SAVED UNDER A NEW NAME (the file with the usual name is open, probably in Excel):")
            out += [f"   {used}   (instead of {wanted})" for wanted, used in self.renamed]
            out.append("")
        if self.combined:
            out.append(f"Combined file: {self.combined.name}   (in {self.combined.parent})")
            for r in self.results:
                if not any(r.supplier == s for s, _ in self.separate):
                    out.append(f"   {r.supplier:<20} {len(r.rows):>4} rows   ({r.file}{_how(r)})")
        if self.separate:
            out.append("")
            out.append("SEPARATE FILES (their final file has a tab per species):")
            for name, path in self.separate:
                n = sum(len(r.rows) for r in self.results if r.supplier == name)
                files = ", ".join(r.file + _how(r) for r in self.results if r.supplier == name)
                out.append(f"   {name:<20} {n:>4} rows   -> {path.name}   (from {files})")
        if self.notes:
            out.append("")
            out.append("New columns / tabs (highlighted in yellow, not yet in the final file):")
            out += [f"   {n}" for n in self.notes]
        fixes = [(r.supplier, c) for r in self.results for c in r.corrections]
        if fixes:
            out.append("")
            out.append("PRICE CHECKS (please look at these - red cells in the Excel; only 'dropped' rows were removed):")
            out += [f"   {s}: {c}" for s, c in fixes]
        warn = [(r.supplier, w) for r in self.results for w in r.warnings]
        if warn:
            out.append("")
            out.append("WARNINGS:")
            out += [f"   {s}: {w}" for s, w in warn]
        skipped = [(r.supplier, s) for r in self.results for s in r.skipped]
        if skipped:
            out.append("")
            out.append("Products with a price that were NOT extracted (unknown product - add it to data/species.json):")
            out += [f"   {s}: {p}" for s, p in skipped[:40]]
            if len(skipped) > 40:
                out.append(f"   ... and {len(skipped) - 40} more")
        if self.errors:
            out.append("")
            out.append("NOT PROCESSED:")
            out += [f"   {e}" for e in self.errors]
        return "\n".join(out) if out else "Nothing to do."


def _how(result):
    """', recognised by its layout' when the supplier didn't come from identifiers or the file name."""
    how = result.identified_by
    return "" if not how or how.startswith(("content", "file name", "chosen")) else f", recognised by {how}"


def run(files, out_dir, progress=None, file_done=None):
    """progress(i, n, name) before each file; file_done(path, result or None, error or None) after it."""
    report = Report()
    for i, f in enumerate(files):
        f = Path(f)
        if progress:
            progress(i, len(files), f.name)
        if f.suffix.lower() not in SUPPORTED:
            res, err = None, f"{f.name}: file type not supported"
        else:
            res, err = extract_file(f)
        if err:
            report.errors.append(err)
        elif res:
            report.results.append(res)
        if file_done:
            file_done(f, res, err)
    with_rows = [r for r in report.results if r.rows]
    if with_rows:
        by_name = {s.name: s for s in suppliers()}
        report.combined, report.separate, report.notes, report.renamed = write_all(with_rows, out_dir, by_name)
    if progress:
        progress(len(files), len(files), "")
    return report

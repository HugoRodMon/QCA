"""Price Extractor (China): the cleaned WeChat market reports (Word files) -> the China sheets' columns."""
import threading
from pathlib import Path

from pricex import china

from .common import load_settings, remember


class Api:
    def __init__(self, host):
        self._host = host

    def state(self):
        return {"out": load_settings().get("china_output", str(Path.home() / "Downloads" / "China prices"))}

    def choose(self):
        paths = self._host.ask_files(load_settings().get("china_input", str(Path.home() / "Downloads")),
                                     ["Word files (*.docx)"])
        if paths:
            remember("china_input", str(Path(paths[0]).parent))
        return paths

    def add(self, paths, known):
        """Files and folders -> the Word files among them, not already in the list."""
        known, files = set(known), []
        for p in map(Path, paths):
            for f in sorted(x for x in p.iterdir() if x.suffix.lower() == ".docx") if p.is_dir() else [p]:
                if str(f) in known or f.suffix.lower() != ".docx" or f.name.startswith("~$"):
                    continue                              # ~$name.docx: Word's lock file while it's open
                known.add(str(f))
                files.append({"path": str(f), "name": f.name})
        return files

    def choose_out(self, current):
        return self._host.ask_folder(current)

    def open_out(self, folder):
        return self._host.open_folder(folder)

    def open_file(self, path):
        return self._host.open_file(path)

    def start(self, paths, out):
        remember("china_output", out)
        threading.Thread(target=self._work, args=(paths, Path(out)), daemon=True).start()

    def _work(self, paths, out):
        try:
            report = china.Report()
            per_file = []
            for path in paths:
                try:
                    r = china.extract(path)
                except Exception as e:
                    per_file.append({"path": path, "error": f"Couldn't read it: {e}"})
                    continue
                report.rows += r.rows
                report.unread += r.unread
                report.notes += r.notes
                per_file.append({"path": path, "rows": len(r.rows)})
            workbook = china.write(report, out) if report.rows or report.unread else None
            sheets = []
            for sheet in china.SHEETS:
                rows = [r for r in report.rows if r.sheet == sheet]
                if rows:
                    sheets.append({"name": sheet, "rows": len(rows), "red": sum(len(r.red) for r in rows)})
            self._host.emit("china.done", {
                "files": per_file, "sheets": sheets, "rows": len(report.rows),
                "red": sum(len(r.red) for r in report.rows),
                "check": [{"line": line, "why": f"Not read: {why}", "kind": "bad"} for line, why in report.unread]
                + [{"line": line, "why": why, "kind": "warn"} for line, why in report.notes],
                "workbook": str(workbook) if workbook else None, "name": workbook.name if workbook else None})
        except Exception as e:                            # never leave the screen stuck
            self._host.emit("china.error", f"Something went wrong: {e}")

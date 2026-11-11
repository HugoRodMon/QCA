"""Fruit Counter: marks every fruit on a picture; the person checks and corrects the marks.

The screen keeps the marks and handles the mouse. This side reads the pictures, counts and saves.
"""
import threading
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font
from PIL import Image

from pricex.output import save_workbook

from . import fruit_count as F
from . import fruit_model as M
from . import lessons as L
from .common import IMAGE_TYPES, data_url, image_files, load_settings, picture_info, remember

SHOWN_SIDE = 3000       # the picture on screen is at most this big; the marks stay in the real picture's pixels


class Picture:
    """One picture and its marks."""

    def __init__(self, path, points=(), detected=0, added=0, removed=0, diameter=None, mode=M.DEFAULT_MODE):
        self.path = Path(path)
        self.mode = mode if mode in M.MODES else M.DEFAULT_MODE     # what was counted (berries, bunches...)
        self.points = [tuple(p) for p in points]        # [(x, y)] in the picture's pixels
        self.detected = detected
        self.added = added
        self.removed = removed
        self.diameter = diameter                        # one fruit, in pixels

    @property
    def count(self):
        return len(self.points)


class Api:
    def __init__(self, host):
        self._host = host
        self._lock = threading.Lock()
        self._path = None       # the picture being counted, kept to count again quickly
        self._rgb = None
        self._read = None       # the same picture as the model has read it

    def state(self):
        settings = load_settings()
        mode = settings.get("fruit_mode", M.DEFAULT_MODE)
        L.send_soon()                                       # lessons left over from last time
        return {"out": settings.get("fruit_output", str(Path.home() / "Downloads" / "Fruit counts")),
                "modes": M.mode_list(), "mode": mode if mode in M.MODES else M.DEFAULT_MODE,
                "lessons": self.lessons()}

    def lessons(self):
        """Sharing corrected counts: on (this PC has the team key), share (the tick), pending (not sent yet)."""
        return {"on": L.access() is not None, "share": load_settings().get("fruit_share", True), "pending": L.pending()}

    def team_key(self, key):
        """Remember the team key if it's right; returns the new lessons state, or None if the key is wrong."""
        return self.lessons() if L.set_team_key(key) else None

    def share(self, on):
        remember("fruit_share", bool(on))

    def choose(self):
        types = "Pictures (" + ";".join(f"*{e}" for e in IMAGE_TYPES) + ")"
        return self._host.ask_files(load_settings().get("images_input", ""), [types])

    def add(self, paths, known):
        known, files = set(known), []
        for f in image_files(paths):
            if str(f) not in known:
                known.add(str(f))
                files.append({"path": str(f), "name": f.name})
        if files:
            remember("images_input", str(Path(files[0]["path"]).parent))
            threading.Thread(target=self._thumbs, args=(files,), daemon=True).start()
        return files

    def _thumbs(self, files):
        for f in files:
            try:
                self._host.emit("fruit.thumb", {"path": f["path"], "thumb": picture_info(f["path"])[2]})
            except Exception:
                pass                                    # the error shows when the picture is opened

    def _pixels(self, path):
        if path != self._path:
            self._rgb, self._path, self._read = F.load_rgb(path), path, None
        return self._rgb

    def load(self, path):
        """The picture to show: {url, width, height} (its real size), or {error}."""
        with self._lock:
            try:
                rgb = self._pixels(path)
                height, width = rgb.shape[:2]
                img = Image.fromarray(rgb)
                img.thumbnail((SHOWN_SIDE, SHOWN_SIDE))
                return {"url": data_url(img, 88), "width": width, "height": height}
            except Exception as e:
                self._path = self._rgb = None
                return {"error": f"Can't open {Path(path).name}: {e}"}

    def detect(self, path, diameter, sensitivity, example=None, mode=M.DEFAULT_MODE):
        """Count. example: (x0, y0, x1, y1) across one thing the person measured, which gives its size and
        colour; without it the count is automatic. mode: what counts as one (see fruit_model.MODES).
        Returns {points, diameter}, {measure: True} when this mode needs one measured first, or {error}."""
        with self._lock:
            try:
                remember("fruit_mode", mode)
                if not example and M.needs_example(mode) and M.available():
                    return {"measure": True}                # a bunch, a punnet...: its size comes from the person
                rgb = self._pixels(path)
                found = None
                if M.available():
                    try:
                        if self._read is None:
                            self._read = M.Picture(rgb)
                        points, size = M.count(self._read, mode, example, float(sensitivity) / 100)
                        if points:
                            found = points, size
                    except Exception:
                        self._read = None                   # the plain counter below still gives a count
                if found is None:
                    if example:
                        found = F.detect_like(rgb, example, float(sensitivity) / 100)
                    else:
                        found = F.detect(rgb, diameter=diameter or None, sensitivity=float(sensitivity) / 100)
                points, size = found
                return {"points": [[float(x), float(y)] for x, y in points], "diameter": float(size)}
            except Exception as e:
                return {"error": f"Counting failed: {e}"}

    def choose_out(self, current):
        return self._host.ask_folder(current)

    def open_out(self, folder):
        return self._host.open_folder(folder)

    def save(self, pictures, out, share=False):
        """share: the person checked every mark, so the pictures can be sent as lessons."""
        remember("fruit_output", out)
        counted = [Picture(p["path"], p["points"], p["detected"], p["added"], p["removed"], p["diameter"], p.get("mode")) for p in pictures]
        threading.Thread(target=self._work, args=(counted, Path(out), pictures if share else []), daemon=True).start()

    def _work(self, pictures, out, lessons):
        try:
            workbook = write_results(pictures, out)
            self._host.emit("fruit.saved", {"workbook": workbook.name, "n": len(pictures), "folder": str(workbook.parent)})
        except Exception as e:
            self._host.emit("fruit.error", f"Could not save: {e}")
            return
        if lessons and L.access() is not None:
            from version import __version__
            for picture in lessons:
                try:
                    L.queue(picture, F.load_rgb(picture["path"]), __version__)
                except Exception:
                    pass                                    # a lesson less; the counts are saved all the same
            L.send_soon()


def write_results(pictures, folder):
    """An Excel with the counts, and a copy of each picture with its marks numbered. Returns the Excel's path."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = "Counts"
    sheet.append(["Picture", "Count", "Counted", "Found automatically", "Added by hand", "Removed by hand"])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for picture in pictures:
        product, _, many, _ = M.MODES[picture.mode]
        what = many.capitalize() if picture.mode == M.DEFAULT_MODE else f"{product}: {many}"
        sheet.append([picture.path.name, picture.count, what, picture.detected, picture.added, picture.removed])
        image = F.annotated(F.load_rgb(picture.path), picture.points, picture.diameter or 40)
        target = folder / f"{picture.path.stem}_counted.jpg"
        n = 2
        while target.exists():
            target = folder / f"{picture.path.stem}_counted ({n}).jpg"
            n += 1
        image.save(target, quality=90)
    sheet.append(["Total", sum(p.count for p in pictures)])
    sheet.cell(sheet.max_row, 1).font = sheet.cell(sheet.max_row, 2).font = Font(bold=True)
    sheet.column_dimensions["A"].width = 42
    for column in "BDEF":
        sheet.column_dimensions[column].width = 18
    sheet.column_dimensions["C"].width = 34
    return save_workbook(book, folder / "Fruit counts.xlsx")

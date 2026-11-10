"""Image Editor: the same edits on many pictures at once, with a live preview. Originals are never touched."""
import threading
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageOps

from . import image_tools as T
from .common import IMAGE_TYPES, data_url, image_files, load_settings, picture_info, remember

PREVIEW_SOURCE = 1400       # the preview works on a copy this big, to be quick


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def make_recipe(d):
    """What the screen sends -> an image_tools.Recipe."""
    size = T.RESOLUTIONS.get(d.get("resolution"))
    if d.get("resolution") == "Custom":
        w, h = int(_number(d.get("custom_w"))), int(_number(d.get("custom_h")))
        size = (w, h) if w > 0 and h > 0 else None
    return T.Recipe(angle=_number(d.get("angle")), flip_h=bool(d.get("flip_h")), flip_v=bool(d.get("flip_v")),
                    ratio=T.RATIOS.get(d.get("ratio")), anchor=d.get("anchor") or "Center", size=size,
                    fit=d.get("fit") or T.FIT_MODES[0], brightness=_number(d.get("brightness"), 100) / 100,
                    contrast=_number(d.get("contrast"), 100) / 100, saturation=_number(d.get("saturation"), 100) / 100,
                    sharpness=_number(d.get("sharpness"), 100) / 100)


class Api:
    def __init__(self, host):
        self._host = host
        self._lock = threading.Lock()
        self._path = None           # the selected picture, in a small copy for a fast preview
        self._source = None
        self._size = None

    def state(self):
        return {"ratios": list(T.RATIOS), "anchors": list(T.ANCHORS), "resolutions": list(T.RESOLUTIONS) + ["Custom"],
                "fits": list(T.FIT_MODES), "formats": list(T.FORMATS),
                "out": load_settings().get("images_output", str(Path.home() / "Downloads" / "Images edited"))}

    def choose(self):
        types = "Pictures (" + ";".join(f"*{e}" for e in IMAGE_TYPES) + ")"
        return self._host.ask_files(load_settings().get("images_input", ""), [types])

    def add(self, paths, known):
        """New pictures for the list. Their thumbnails arrive one by one as 'image.thumb'."""
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
                w, h, thumb = picture_info(f["path"])
                self._host.emit("image.thumb", {"path": f["path"], "w": w, "h": h, "thumb": thumb})
            except Exception as e:
                self._host.emit("image.thumb", {"path": f["path"], "error": str(e)})

    def _load(self, path):
        if path != self._path:
            with Image.open(path) as img:
                w, h = img.size
                self._size = (h, w) if img.getexif().get(274) in (5, 6, 7, 8) else (w, h)   # phone pictures
                img.draft("RGB", (PREVIEW_SOURCE, PREVIEW_SOURCE))
                source = ImageOps.exif_transpose(img)
                source.thumbnail((PREVIEW_SOURCE, PREVIEW_SOURCE))
                source.load()
            self._path, self._source = path, source

    def preview(self, path, recipe, original, width, height):
        """The selected picture with the edits, to fit in width x height."""
        with self._lock:
            try:
                self._load(path)
            except Exception as e:
                self._path = self._source = None
                return {"error": f"Can't open this picture: {e}"}
            recipe = make_recipe(recipe)
            final = T.result_size(self._size, recipe)
            if recipe.size and max(recipe.size) > 1000:      # only the shape matters for a preview: keep it fast
                scale = 1000 / max(recipe.size)
                recipe = replace(recipe, size=(max(1, round(recipe.size[0] * scale)), max(1, round(recipe.size[1] * scale))))
            try:
                result = self._source.copy() if original else T.apply(self._source, recipe)
                result.thumbnail((max(int(width), 50), max(int(height), 50)))
                return {"url": data_url(result), "original": self._size, "result": final}
            except Exception as e:
                return {"error": f"Can't apply these edits: {e}"}

    def choose_out(self, current):
        return self._host.ask_folder(current)

    def open_out(self, folder):
        return self._host.open_folder(folder)

    def save(self, paths, out, recipe, suffix, format_name, quality):
        remember("images_output", out)
        args = (paths, Path(out), make_recipe(recipe), suffix, T.FORMATS.get(format_name), int(quality))
        threading.Thread(target=self._work, args=args, daemon=True).start()

    def _work(self, paths, out, recipe, suffix, extension, quality):
        emit = self._host.emit
        try:
            saved, failed = T.process_batch(paths, out, recipe, suffix, extension, quality,
                                            lambda i, n, name: emit("image.progress", {"i": i, "n": n, "name": name}))
            emit("image.done", {"saved": len(saved), "folder": str(out), "failed": [{"name": n, "error": e} for n, e in failed]})
        except Exception as e:
            emit("image.error", f"The pictures could not be saved: {e}. Try another output folder.")

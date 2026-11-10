"""What all DQS apps share: settings, file helpers, and the Host that connects them to the window."""
import base64
import io
import json
import os
from pathlib import Path

IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")

# settings live in %APPDATA%: next to the code would be a temporary folder inside the .exe
SETTINGS = Path(os.environ.get("APPDATA", Path.home())) / "PriceExtractor" / "settings.json"


def load_settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data):
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, indent=1), encoding="utf-8")
    except Exception:
        pass


def remember(key, value):
    """Keep one setting. Read fresh: all the apps share this file."""
    data = load_settings()
    data[key] = value
    save_settings(data)


def image_files(paths):
    """Expand dropped files and folders into the pictures they contain."""
    out = []
    for p in map(Path, paths):
        items = sorted(p.iterdir()) if p.is_dir() else [p]
        out += [f for f in items if f.is_file() and f.suffix.lower() in IMAGE_TYPES]
    return out


def open_folder(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if hasattr(os, "startfile"):
        os.startfile(folder)


def data_url(img, quality=85):
    """A PIL picture as something an <img> can show. JPG unless it has transparency."""
    buffer = io.BytesIO()
    if img.mode in ("RGBA", "LA", "PA"):
        img.save(buffer, "PNG")
        kind = "png"
    else:
        img.convert("RGB").save(buffer, "JPEG", quality=quality)
        kind = "jpeg"
    return f"data:image/{kind};base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"


def picture_info(path, thumb_side=132):
    """(width, height, thumbnail data url) of a picture, turned the way it was taken. Quick: reads it small."""
    from PIL import Image, ImageOps
    with Image.open(path) as img:
        w, h = img.size
        if img.getexif().get(274) in (5, 6, 7, 8):        # phone pictures
            w, h = h, w
        img.draft("RGB", (thumb_side * 2, thumb_side * 2))
        small = ImageOps.exif_transpose(img)
        small.thumbnail((thumb_side, thumb_side))
        return w, h, data_url(small.convert("RGB"), 75)


class Host:
    """What an app can ask of the window: pop-up dialogs, messages to its screen, opening files."""

    def __init__(self):
        self.window = None                  # set once the window exists

    def emit(self, event, payload=None):
        """Tell the screen something happened. Safe from any thread."""
        if self.window:
            self.window.evaluate_js(f"dqs.emit({json.dumps(event)}, {json.dumps(payload)})")

    def ask_files(self, directory="", types=()):
        """Choose files. types: e.g. ['Pictures (*.jpg;*.png)']. Returns a list of paths."""
        import webview
        chosen = self.window.create_file_dialog(webview.FileDialog.OPEN, directory=str(directory or ""), allow_multiple=True,
                                                file_types=tuple(types) + ("All files (*.*)",))
        return list(chosen or [])

    def ask_folder(self, directory=""):
        import webview
        chosen = self.window.create_file_dialog(webview.FileDialog.FOLDER, directory=str(directory or ""))
        return chosen[0] if chosen else None

    def open_folder(self, folder):
        try:
            open_folder(folder)
        except Exception as e:
            return str(e)

    def open_file(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            return str(e)


def full_speed():
    """Ask Windows not to slow this program down when its window isn't in front ("power throttling" moves
    such programs to the slow, power-saving cores, which makes counting with the model 10 times slower)."""
    try:
        import ctypes
        from ctypes import wintypes

        class State(ctypes.Structure):
            _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

        state = State(1, 0x1, 0x0)      # execution speed throttling: off
        kernel = ctypes.windll.kernel32
        kernel.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        return bool(kernel.SetProcessInformation(kernel.GetCurrentProcess(), 4, ctypes.byref(state), ctypes.sizeof(state)))
    except Exception:
        return False

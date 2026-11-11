"""DQS Apps: the team's little apps in one window. Run:  python dqs.py  (or the DQSApps.exe)

The screens are in ui/ (HTML, CSS, JavaScript), shown by pywebview in the Edge WebView2 that comes with Windows.
The work is done here in Python: each app has an Api class in apps/, which the screens call as pywebview.api.<app>.
"""
import base64
import html
import os
import re
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import updater  # noqa: E402
from apps import common, locked  # noqa: E402
from version import __version__  # noqa: E402

UI = Path(__file__).resolve().parent / "ui"
UI_SCRIPTS = ("shell.js", "price.js", "image.js", "fruit.js")
WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def page():
    """The whole interface as one page, so it needs no web server."""
    text = (UI / "index.html").read_text(encoding="utf-8")
    text = text.replace("/*CSS*/", (UI / "style.css").read_text(encoding="utf-8"))
    scripts = "\n".join((UI / name).read_text(encoding="utf-8") for name in UI_SCRIPTS)
    logo = "data:image/png;base64," + base64.b64encode((UI / "logo.png").read_bytes()).decode()
    return text.replace("/*VERSION*/", __version__).replace("/*LOGO*/", logo).replace("/*SCRIPTS*/", scripts)


def _centre(window):
    """Open centred on the free part of the screen the mouse is on (above the taskbar), made smaller first if
    it wouldn't fit (small or zoomed laptop screens). Runs just before the window is shown."""
    try:
        from System.Drawing import Rectangle, Size
        from System.Windows.Forms import Cursor, FormStartPosition, Screen
        form = window.native
        area = Screen.FromPoint(Cursor.Position).WorkingArea
        width, height = min(form.Width, int(area.Width * 0.96)), min(form.Height, int(area.Height * 0.96))
        form.MinimumSize = Size(min(form.MinimumSize.Width, width), min(form.MinimumSize.Height, height))
        form.StartPosition = FormStartPosition.Manual
        form.Bounds = Rectangle(area.X + (area.Width - width) // 2, area.Y + (area.Height - height) // 2, width, height)
    except Exception:
        pass                                    # pywebview centres it itself, just without these checks


def summary(notes):
    """The first real line of a release's notes, as plain text: no markdown, no links, not GitHub's
    'What's Changed' / 'Full Changelog' lines (those say nothing to the team)."""
    for line in (notes or "").splitlines():
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)          # [text](link) -> text
        line = re.sub(r"https?://\S+", "", line)
        line = re.sub(r"[*_`#>]+", "", line).strip(" -:")
        if line and not re.match(r"(?i)(what's changed|full changelog|new contributors)\b", line):
            return line
    return ""


class Private:
    """What pywebview sees of the unlocked apps: every call goes through call(app, method, args)."""

    def __init__(self, host):
        self._host = host
        self._apps = {}

    def unlock(self, key):
        """The private apps' screens, or None if the key is wrong. Checking takes a moment, on purpose.
        A right key is remembered on this PC (like the Fruit Counter's team key), so it's asked only once."""
        apps = locked.unlock(key.strip()) if key and key.strip() else None
        if not apps:
            return None
        if common.load_settings().get("private_key") != key.strip():
            common.remember("private_key", key.strip())
        screens = []
        for app in apps:
            try:
                module = locked.load_module(app)
                self._apps[app["id"]] = module.Api(self._host)
                screens.append({"id": app["id"], "code": app["code"], "title": app["title"], "sub": app["description"],
                                "html": module.HTML, "js": module.JS})
            except Exception as e:                     # one broken app shouldn't hide the others
                screens.append({"id": app["id"], "code": app["code"], "title": app["title"], "sub": app["description"],
                                "html": f'<div class="banner bad" style="margin:24px 28px">This app couldn\'t start: {html.escape(str(e))}</div>', "js": ""})
        return screens

    def remembered(self):
        """The private apps' screens if this PC has a key that still opens them (else None, and a key that no
        longer works, after the key was changed, is forgotten)."""
        key = common.load_settings().get("private_key")
        if not key:
            return None
        screens = self.unlock(key)
        if screens is None:
            common.remember("private_key", "")
        return screens

    def call(self, app, method, args):
        if method.startswith("_"):
            raise ValueError("not an app method")
        return getattr(self._apps[app], method)(*args)


class Updates:
    def __init__(self, host):
        self._host = host
        self._info = None

    def check(self):
        """In the background when the window opens. Only the built .exe updates itself."""
        updater.cleanup_old()
        if not updater.is_frozen():
            return
        self._info = updater.check()
        if self._info:
            line = summary(self._info["notes"])
            self._host.emit("update.available", {"version": self._info["version"],
                                                 "notes": line[:80] + ("…" if len(line) > 80 else "")})

    def install(self):
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        def progress(done, total):
            self._host.emit("update.progress", done * 100 // (total or 1))
        try:
            updater.install_and_restart(updater.download(self._info, progress))
        except Exception as e:
            self._host.emit("update.error", f"The update could not be installed: {e}. You can keep using this version.")
            return
        self._host.window.destroy()


class Api:
    """Everything the screens can call. pywebview exposes public attributes only, so the rest starts with _."""

    def __init__(self, host):
        from apps import fruit_counter, image_editor, price_extractor
        self._host = host
        self.price = price_extractor.Api(host)
        self.image = image_editor.Api(host)
        self.fruit = fruit_counter.Api(host)
        self.private = Private(host)
        self.updates = Updates(host)


def _listen_for_drops(window, host):
    """A file dropped anywhere in the window. The screen sends it to whichever app is open."""
    from webview.dom import DOMEventHandler

    def dropped(event):
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [f["pywebviewFullPath"] for f in files if f.get("pywebviewFullPath")]
        host.emit("drop", paths)

    window.dom.document.events.drop += DOMEventHandler(dropped, True, True)


def show_message(title, text):
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)


def open_window():
    import webview
    common.full_speed()
    host = common.Host()
    api = Api(host)
    window = webview.create_window("DQS Apps", html=page(), js_api=api, width=1280, height=800, min_size=(1160, 700),
                                   background_color="#141518", text_select=True)
    host.window = window

    def ready():
        _listen_for_drops(window, host)
        api.updates.check()

    window.events.before_show += _centre
    window.events.loaded += lambda: threading.Thread(target=ready, daemon=True).start()
    webview.start(gui="edgechromium", icon=str(UI / "icon.ico"))


def self_check():
    """Every app and library really is in this build. Returns the problems found (used by the release check).
    With DQS_TEST_KEY set, the private apps are also decrypted and started."""
    problems = []
    for name in ("apps.price_extractor", "apps.image_editor", "apps.fruit_counter", "cv2", "numpy", "webview", "clr",
                 "webview.platforms.edgechromium", "cryptography.fernet", "pdfplumber", "openpyxl.styles", "uuid",
                 "winrt.windows.media.ocr", "rapidocr_onnxruntime"):
        try:
            __import__(name)
        except Exception as e:
            problems.append(f"{name}: {e}")
    for name in ("index.html", "style.css", "logo.png", "icon.ico") + UI_SCRIPTS:
        if not (UI / name).exists():
            problems.append(f"the screen file {name} is missing")
    if not locked.BUNDLE.exists():
        problems.append("the encrypted private apps are missing")
    from apps import lessons
    if not lessons.BUNDLE.exists():
        problems.append("the Fruit Counter's encrypted Drive access (lessons.enc) is missing")
    try:
        import numpy as np

        from apps.fruit_count import detect
        detect(np.full((60, 60, 3), 128, np.uint8))
    except Exception as e:
        problems.append(f"fruit detection: {e}")
    try:
        import numpy as np

        from apps import fruit_model
        if not fruit_model.available():
            problems.append("the Fruit Counter's model files are missing")
        else:
            fruit_model.count(fruit_model.Picture(np.full((60, 80, 3), 128, np.uint8)))
    except Exception as e:
        problems.append(f"fruit counting model: {e}")
    key = os.environ.get("DQS_TEST_KEY")
    if key:
        screens = Private(common.Host()).unlock(key)
        if not screens:
            problems.append("the test key doesn't open the private apps")
        for screen in screens or ():
            if not screen["js"]:
                problems.append(f"{screen['title']} didn't start")
    return problems


def extract_without_window(args):
    """DQSApps.exe --extract <files or folders> -o <output folder>   (writes report.txt there)"""
    from apps.price_extractor import run_without_window
    from pricex.base import suppliers
    report, out = run_without_window(args)
    problems = self_check()
    check = "OK" if not problems else "PROBLEMS: " + "; ".join(problems)
    (out / "report.txt").write_text(f"DQS Apps v{__version__}\nSuppliers loaded: {len(suppliers())}\nApps check: {check}\n\n"
                                    f"{report.text()}\n", encoding="utf-8")


def update_without_asking():
    """DQSApps.exe --update : install the latest version if there is one, then start it."""
    updater.cleanup_old()
    info = updater.check()
    if info and updater.is_frozen():
        updater.install_and_restart(updater.download(info))


def main():
    if "--extract" in sys.argv:
        extract_without_window(sys.argv[1:])
    elif "--update" in sys.argv:
        update_without_asking()
    else:
        try:
            open_window()
        except Exception as e:
            # nearly always the WebView2 runtime that shows the window: Windows 11 has it, an old Windows 10 may not
            show_message("DQS Apps can't open its window",
                         f"{e}\n\nDQS Apps needs Microsoft Edge WebView2, which is free and comes with most Windows PCs. "
                         f"Install the \"Evergreen Bootstrapper\" from:\n{WEBVIEW2_URL}\n\nThen open DQS Apps again.")


if __name__ == "__main__":
    main()

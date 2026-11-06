"""DQS Apps: the home screen of the team's little apps. Run:  python dqs.py  (or the DQSApps.exe)"""
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import updater  # noqa: E402
from apps import common, locked  # noqa: E402
from apps.common import ACCENT, BAD, BG, BORDER, FG, MUTED, PANEL  # noqa: E402
from version import __version__  # noqa: E402


def _price_extractor(master):
    from apps.price_extractor import open_app
    return open_app(master)


def _image_editor(master):
    from apps.image_editor import open_app
    return open_app(master)


def _fruit_counter(master):
    from apps.fruit_counter import open_app
    return open_app(master)


PUBLIC_APPS = [
    ("Price Extractor - Europe", "Daily supplier price lists (pdf, WhatsApp, web, Excel, pictures) to Excel.", _price_extractor),
    ("Image Editor", "Edit many pictures at once: rotate, crop to a ratio or resolution, brightness...", _image_editor),
    ("Fruit Counter", "Counts the fruit in a picture. You check and correct the marks with a click.", _fruit_counter),
]


class Home:
    def __init__(self):
        self.root = common.new_root()
        self.root.title(f"DQS Apps  v{__version__}")
        w, h = 620, 470
        self.root.geometry(f"{w}x{h}+{(self.root.winfo_screenwidth() - w) // 2}+{(self.root.winfo_screenheight() - h) // 3}")
        self.root.minsize(520, 400)
        self.root.configure(bg=BG)
        common.apply_style()
        self.open_windows = {}                       # title -> app window, to bring it back instead of opening twice
        self._build()
        updater.cleanup_old()
        if updater.is_frozen():                      # only the built .exe updates itself
            threading.Thread(target=self._check_update, daemon=True).start()

    # ------------------------------------------------------------ layout
    def _build(self):
        top = ttk.Frame(self.root, padding=(20, 18, 20, 6))
        top.pack(fill="x")
        tk.Label(top, text="DQS Apps", bg=BG, fg=FG, font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(top, text=f"v{__version__}", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=8, pady=(8, 0))

        self.cards = ttk.Frame(self.root, padding=(20, 6))
        self.cards.pack(fill="both", expand=True)
        for title, description, opener in PUBLIC_APPS:
            self._add_card(title, description, opener)

        bottom = ttk.Frame(self.root, padding=(20, 6, 20, 16))
        bottom.pack(fill="x")
        self.unlock_btn = ttk.Button(bottom, text="Unlock more apps", command=self.ask_key)
        self.unlock_btn.pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="determinate", style="Horizontal.TProgressbar", length=140)
        self.status = ttk.Label(bottom, text="", style="Muted.TLabel")
        self.status.pack(side="right")

    def _add_card(self, title, description, opener, private=False):
        card = tk.Frame(self.cards, bg=PANEL, cursor="hand2", highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", pady=5)
        name = tk.Label(card, text=title + ("   (private)" if private else ""), bg=PANEL, fg=FG, anchor="w",
                        font=("Segoe UI", 11, "bold"))
        name.pack(fill="x", padx=14, pady=(9, 0))
        text = tk.Label(card, text=description, bg=PANEL, fg=MUTED, anchor="w", justify="left",
                        font=("Segoe UI", 9), wraplength=540)
        text.pack(fill="x", padx=14, pady=(0, 9))

        def go(_event=None):
            self.open_app(title, opener)

        for widget in (card, name, text):
            widget.bind("<Button-1>", go)
            widget.bind("<Enter>", lambda e: card.configure(highlightbackground=ACCENT))
            widget.bind("<Leave>", lambda e: card.configure(highlightbackground=BORDER))

    def open_app(self, title, opener):
        win = self.open_windows.get(title)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.focus_force()
            return
        try:
            app = opener(self.root)
        except Exception as e:                       # a missing part shouldn't take the whole suite down
            messagebox.showerror(title, f"This app couldn't start:\n{e}", parent=self.root)
            return
        self.open_windows[title] = app.root
        app.root.lift()

    # ------------------------------------------------------------ private apps
    def ask_key(self):
        win = tk.Toplevel(self.root)
        win.title("Unlock more apps")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self.root)
        frame = ttk.Frame(win, padding=18)
        frame.pack()
        ttk.Label(frame, text="Enter the secret key:").pack(anchor="w")
        key = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=key, show="•", width=38)
        entry.pack(pady=8)
        entry.focus_set()
        message = tk.Label(frame, text="", bg=BG, fg=BAD, font=("Segoe UI", 9))
        message.pack(anchor="w")
        button = ttk.Button(frame, text="Unlock")
        button.pack(anchor="e", pady=(6, 0))

        def submit(_event=None):
            button.configure(state="disabled")
            message.configure(text="")
            threading.Thread(target=work, args=(key.get().strip(),), daemon=True).start()

        def work(value):                             # checking a key takes a moment, on purpose
            apps = locked.unlock(value) if value else None
            self.root.after(0, finish, apps)

        def finish(apps):
            if not win.winfo_exists():
                return
            button.configure(state="normal")
            if not apps:
                message.configure(text="That key isn't correct.")
                key.set("")
                return
            win.destroy()
            self.show_private(apps)

        button.configure(command=submit)
        entry.bind("<Return>", submit)

    def show_private(self, apps):
        for app in apps:
            def opener(master, app=app):
                return locked.load_module(app).open_app(master)
            self._add_card(app["title"], app["description"], opener, private=True)
        self.unlock_btn.pack_forget()
        self.root.geometry(f"{self.root.winfo_width()}x{self.root.winfo_height() + 80 * len(apps)}")

    # ------------------------------------------------------------ updates
    def _check_update(self):
        info = updater.check()
        if info:
            self.root.after(0, self._offer_update, info)

    def _offer_update(self, info):
        notes = info["notes"][:600] + ("..." if len(info["notes"]) > 600 else "")
        msg = f"Version {info['version']} is available (you have {__version__}).\n\n{notes}\n\nUpdate now? The app will restart."
        if not messagebox.askyesno("Update available", msg, parent=self.root):
            return
        self.status.configure(text="Downloading update...")
        self.progress.pack(side="right", padx=8)
        threading.Thread(target=self._do_update, args=(info,), daemon=True).start()

    def _do_update(self, info):
        def progress(done, total):
            self.root.after(0, lambda: (self.progress.configure(maximum=total or 1, value=done),
                                        self.status.configure(text=f"Downloading update... {done * 100 // (total or 1)}%")))
        try:
            updater.install_and_restart(updater.download(info, progress))
        except Exception as e:
            reason = str(e)                          # `e` doesn't exist any more when the window shows the message
            self.root.after(0, lambda: (self.progress.pack_forget(), self.status.configure(text=""),
                                        messagebox.showerror("Update failed", f"The update could not be installed:\n{reason}\n\n"
                                                             "You can keep using this version.", parent=self.root)))
            return
        self.root.after(0, self.root.destroy)

    def mainloop(self):
        self.root.mainloop()


def self_check():
    """Every app and library really is in this build. Returns the problems found (used by the release check).
    With DQS_TEST_KEY set, the private apps are also decrypted and opened."""
    problems = []
    for name in ("apps.price_extractor", "apps.image_editor", "apps.fruit_counter", "PIL.ImageTk", "cv2", "numpy",
                 "cryptography.fernet", "pdfplumber", "openpyxl.styles", "uuid", "winrt.windows.media.ocr",
                 "rapidocr_onnxruntime", "tkinterdnd2"):
        try:
            __import__(name)
        except Exception as e:
            problems.append(f"{name}: {e}")
    if not locked.BUNDLE.exists():
        problems.append("the encrypted private apps are missing")
    try:
        import numpy as np

        from apps.fruit_count import detect
        detect(np.full((60, 60, 3), 128, np.uint8))
    except Exception as e:
        problems.append(f"fruit detection: {e}")
    key = os.environ.get("DQS_TEST_KEY")
    if key:
        apps = locked.unlock(key)
        if not apps:
            problems.append("the test key doesn't open the private apps")
        else:
            root = common.new_root()
            for app in apps:
                try:
                    locked.load_module(app).open_app(root)
                except Exception as e:
                    problems.append(f"{app['title']}: {e}")
            root.destroy()
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
        Home().mainloop()


if __name__ == "__main__":
    main()

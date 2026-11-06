"""What all DQS apps share: colours, widget styles, settings and drag & drop."""
import json
import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND = True
except ImportError:                     # still works without drag & drop
    DND_FILES, TkinterDnD = None, None
    DND = False

BG, PANEL, FG, MUTED, ACCENT = "#1f2126", "#2a2d34", "#e0e2e6", "#8b909a", "#5a8c74"
BORDER, DARK, BAD = "#3a3d45", "#18191d", "#e57373"
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


def new_root():
    return TkinterDnD.Tk() if DND else tk.Tk()


def apply_style():
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("TFrame", background=BG)
    s.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
    s.configure("Muted.TLabel", foreground=MUTED, font=("Segoe UI", 9))
    s.configure("Head.TLabel", font=("Segoe UI", 10, "bold"))
    s.configure("TButton", font=("Segoe UI", 10), padding=(12, 6))
    s.configure("Go.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 8), background=ACCENT, foreground="white")
    s.map("Go.TButton", background=[("active", "#6ba487"), ("disabled", BORDER)])
    s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=24, font=("Segoe UI", 9))
    s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
    s.map("Treeview", background=[("selected", "#3a5a47")])
    s.configure("Horizontal.TProgressbar", background=ACCENT)
    s.configure("TCheckbutton", background=BG, foreground=FG, font=("Segoe UI", 10))
    s.map("TCheckbutton", background=[("active", BG)])
    s.configure("Horizontal.TScale", background=BG)


def new_window(master, title, size, minsize=(600, 400)):
    win = tk.Toplevel(master)
    win.title(title)
    w, h = size
    win.geometry(f"{w}x{h}+{max(0, (win.winfo_screenwidth() - w) // 2)}+{max(0, (win.winfo_screenheight() - h) // 3)}")
    win.minsize(*minsize)
    win.configure(bg=BG)
    return win


def drop_zone(parent, text, on_files, on_click=None):
    """The dark 'drop files here' area. on_files gets a list of paths."""
    zone = tk.Label(parent, text=text, bg=DARK, fg=MUTED, font=("Segoe UI", 11), cursor="hand2",
                    highlightthickness=2, highlightbackground=BORDER)
    if on_click:
        zone.bind("<Button-1>", lambda e: on_click())
    if DND:
        def dropped(event):
            zone.configure(highlightbackground=BORDER, fg=MUTED)
            on_files(list(zone.tk.splitlist(event.data)))
        zone.drop_target_register(DND_FILES)
        zone.dnd_bind("<<Drop>>", dropped)
        zone.dnd_bind("<<DragEnter>>", lambda e: zone.configure(highlightbackground=ACCENT, fg=ACCENT))
        zone.dnd_bind("<<DragLeave>>", lambda e: zone.configure(highlightbackground=BORDER, fg=MUTED))
    return zone


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

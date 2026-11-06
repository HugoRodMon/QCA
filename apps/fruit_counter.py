"""Fruit Counter: marks every fruit on a picture; the person checks and corrects the marks.

Left click = add a mark. Right click = remove the nearest one. Mouse wheel = zoom, drag = move around.
"""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
from openpyxl import Workbook
from openpyxl.styles import Font
from PIL import Image, ImageTk

from pricex.output import save_workbook

from . import fruit_count as F
from .common import (ACCENT, BG, BORDER, DARK, DND, FG, IMAGE_TYPES, drop_zone, image_files, load_settings,
                     new_window, open_folder, save_settings)

CLICK_MOVE = 4          # moving less than this many pixels is a click, more is a drag


class Picture:
    """One picture and its marks."""

    def __init__(self, path):
        self.path = Path(path)
        self.points = []            # [(x, y)] in the picture's pixels
        self.detected = 0
        self.added = 0
        self.removed = 0
        self.diameter = None        # one fruit, in pixels
        self.done = False           # detection has run

    @property
    def count(self):
        return len(self.points)


class FruitCounter:
    def __init__(self, master):
        self.root = new_window(master, "Fruit Counter", (1120, 740), (860, 560))
        self.settings = load_settings()
        self.pictures = []
        self.current = None
        self.rgb = None             # the current picture's pixels
        self.photo = None
        self.zoom, self.ox, self.oy = 1.0, 0.0, 0.0       # screen = picture * zoom + offset
        self.history = []           # undo
        self.measuring = False
        self.press = None
        self.sensitivity = tk.DoubleVar(value=70)
        self.out_dir = tk.StringVar(value=self.settings.get("fruit_output", str(Path.home() / "Downloads" / "Fruit counts")))
        self._build()
        for key, action in (("<Control-z>", self.undo), ("<Control-Z>", self.undo)):
            self.root.bind(key, lambda e, a=action: a())

    # ------------------------------------------------------------ layout
    def _build(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, width=270)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        hint = "Drop pictures or folders here\nor click to choose" if DND else "Click to choose pictures"
        drop_zone(left, hint, self.add, self.choose).pack(fill="x", ipady=16)

        box = ttk.Frame(left)
        box.pack(fill="both", expand=True, pady=8)
        self.tree = ttk.Treeview(box, columns=("name", "count"), show="headings", selectmode="browse")
        self.tree.heading("name", text="Picture")
        self.tree.heading("count", text="Count")
        self.tree.column("name", width=190)
        self.tree.column("count", width=55, anchor="e", stretch=False)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.select())

        ttk.Label(left, text="Total of all pictures", style="Muted.TLabel").pack(anchor="w")
        self.total_label = tk.Label(left, text="0", bg=BG, fg=FG, font=("Segoe UI", 16, "bold"))
        self.total_label.pack(anchor="w")

        ttk.Label(left, text="Save to:", style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
        row = ttk.Frame(left)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.out_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="...", width=3, command=self.choose_out).pack(side="left", padx=(3, 0))
        ttk.Button(row, text="Open", width=5, command=lambda: open_folder(self.out_dir.get())).pack(side="left", padx=(3, 0))
        self.save_btn = ttk.Button(left, text="Save results", style="Go.TButton", command=self.save)
        self.save_btn.pack(fill="x", pady=(8, 0))

        middle = ttk.Frame(main)
        middle.pack(side="left", fill="both", expand=True, padx=(12, 0))

        top = ttk.Frame(middle)
        top.pack(fill="x", pady=(0, 6))
        self.count_label = tk.Label(top, text="-", bg=BG, fg=ACCENT, font=("Segoe UI", 24, "bold"))
        self.count_label.pack(side="left")
        self.detail_label = ttk.Label(top, text="", style="Muted.TLabel")
        self.detail_label.pack(side="left", padx=10, pady=(10, 0))
        ttk.Button(top, text="Undo", command=self.undo).pack(side="right")
        ttk.Button(top, text="Fit", command=self.fit).pack(side="right", padx=4)

        self.canvas = tk.Canvas(middle, bg=DARK, highlightthickness=1, highlightbackground=BORDER, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)

        controls = ttk.Frame(middle)
        controls.pack(fill="x", pady=(6, 0))
        self.measure_btn = ttk.Button(controls, text="Measure one fruit", command=self.start_measuring)
        self.measure_btn.pack(side="left")
        self.size_label = ttk.Label(controls, text="Fruit size: -", style="Muted.TLabel", width=20)
        self.size_label.pack(side="left", padx=8)
        ttk.Label(controls, text="Finds:  fewer").pack(side="left")
        ttk.Scale(controls, from_=0, to=100, variable=self.sensitivity, orient="horizontal", length=130).pack(side="left", padx=4)
        ttk.Label(controls, text="more").pack(side="left")
        ttk.Button(controls, text="Count again", command=self.count_again).pack(side="left", padx=10)
        self.help = ttk.Label(middle, style="Muted.TLabel",
                              text="Check the marks: left click adds, right click removes, wheel zooms, drag moves around.")
        self.help.pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------------------ files
    def choose(self):
        types = " ".join(f"*{e}" for e in IMAGE_TYPES)
        paths = filedialog.askopenfilenames(parent=self.root, title="Choose pictures", filetypes=[("Pictures", types), ("All files", "*.*")])
        if paths:
            self.add(paths)

    def add(self, paths):
        first_new = None
        known = {p.path for p in self.pictures}
        for f in image_files(paths):
            if f in known:
                continue
            picture = Picture(f)
            self.pictures.append(picture)
            self.tree.insert("", "end", iid=str(f), values=(f.name, ""))
            first_new = first_new or str(f)
        if first_new and self.current is None:
            self.tree.selection_set(first_new)

    def choose_out(self):
        d = filedialog.askdirectory(parent=self.root, title="Where to save the results", initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    def select(self):
        selected = self.tree.selection()
        if not selected:
            return
        picture = next(p for p in self.pictures if str(p.path) == selected[0])
        if picture is self.current:
            return
        try:
            self.rgb = F.load_rgb(picture.path)
        except Exception as e:
            messagebox.showerror("Fruit Counter", f"Can't open {picture.path.name}:\n{e}", parent=self.root)
            return
        self.current = picture
        self.history = []
        self.measuring = False
        self.help.configure(text="Check the marks: left click adds, right click removes, wheel zooms, drag moves around.")
        self.fit()
        if not picture.done:
            self.detect()
        self.refresh()

    # ------------------------------------------------------------ detection
    def detect(self, diameter=None):
        picture = self.current
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            picture.points, picture.diameter = F.detect(self.rgb, diameter=diameter or picture.diameter,
                                                        sensitivity=self.sensitivity.get() / 100)
        except Exception as e:
            messagebox.showerror("Fruit Counter", f"Counting failed:\n{e}", parent=self.root)
        finally:
            self.root.configure(cursor="")
        picture.detected, picture.added, picture.removed = len(picture.points), 0, 0
        picture.done = True
        self.history = []

    def count_again(self):
        """Run the detection again with the current size and sensitivity (corrections are replaced)."""
        if self.current is None:
            return
        if self.current.added or self.current.removed:
            if not messagebox.askyesno("Fruit Counter", "Counting again replaces your corrections on this picture. Continue?", parent=self.root):
                return
        self.detect()
        self.refresh()

    def start_measuring(self):
        if self.current is None:
            return
        self.measuring = True
        self.help.configure(text="Drag across ONE fruit, from edge to edge. The picture is then counted again with that size.")

    # ------------------------------------------------------------ mouse
    def to_picture(self, x, y):
        return (x - self.ox) / self.zoom, (y - self.oy) / self.zoom

    def on_wheel(self, event):
        if self.rgb is None:
            return
        factor = 1.25 if event.delta > 0 else 0.8
        new = min(12.0, max(self.fit_zoom() * 0.5, self.zoom * factor))
        px, py = self.to_picture(event.x, event.y)
        self.ox, self.oy = event.x - px * new, event.y - py * new       # zoom around the mouse
        self.zoom = new
        self.draw()

    def on_press(self, event):
        self.press = (event.x, event.y, self.ox, self.oy)

    def on_drag(self, event):
        if self.press is None or self.rgb is None:
            return
        x, y, ox, oy = self.press
        if self.measuring:
            self.canvas.delete("measure")
            self.canvas.create_line(x, y, event.x, event.y, fill="#ffd54a", width=2, tags="measure")
            return
        if abs(event.x - x) + abs(event.y - y) > CLICK_MOVE:
            self.ox, self.oy = ox + event.x - x, oy + event.y - y
            self.draw()

    def on_release(self, event):
        if self.press is None or self.current is None:
            self.press = None
            return
        x, y, _, _ = self.press
        self.press = None
        moved = abs(event.x - x) + abs(event.y - y)
        if self.measuring:
            self.canvas.delete("measure")
            if moved > CLICK_MOVE:
                self.measuring = False
                self.help.configure(text="Check the marks: left click adds, right click removes, wheel zooms, drag moves around.")
                diameter = ((event.x - x) ** 2 + (event.y - y) ** 2) ** 0.5 / self.zoom
                self.current.diameter = diameter
                self.detect(diameter)
                self.refresh()
            return
        if moved <= CLICK_MOVE:
            px, py = self.to_picture(event.x, event.y)
            height, width = self.rgb.shape[:2]
            if 0 <= px < width and 0 <= py < height:
                self.history.append(("add", (px, py)))
                self.current.points.append((px, py))
                self.current.added += 1
                self.refresh()

    def on_right_click(self, event):
        picture = self.current
        if picture is None or not picture.points:
            return
        px, py = self.to_picture(event.x, event.y)
        index = min(range(len(picture.points)), key=lambda i: (picture.points[i][0] - px) ** 2 + (picture.points[i][1] - py) ** 2)
        nx, ny = picture.points[index]
        reach = max((picture.diameter or 40) * 0.6, 12 / self.zoom)
        if (nx - px) ** 2 + (ny - py) ** 2 <= reach ** 2:
            self.history.append(("remove", picture.points.pop(index)))
            picture.removed += 1
            self.refresh()

    def undo(self):
        if not self.history or self.current is None:
            return
        action, point = self.history.pop()
        if action == "add":
            self.current.points.remove(point)
            self.current.added -= 1
        else:
            self.current.points.append(point)
            self.current.removed -= 1
        self.refresh()

    # ------------------------------------------------------------ drawing
    def fit_zoom(self):
        height, width = self.rgb.shape[:2]
        return min((self.canvas.winfo_width() - 4) / width, (self.canvas.winfo_height() - 4) / height, 4.0)

    def fit(self):
        if self.rgb is None:
            return
        self.root.update_idletasks()
        height, width = self.rgb.shape[:2]
        self.zoom = max(0.01, self.fit_zoom())
        self.ox = (self.canvas.winfo_width() - width * self.zoom) / 2
        self.oy = (self.canvas.winfo_height() - height * self.zoom) / 2
        self.draw()

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        if self.rgb is None:
            return
        height, width = self.rgb.shape[:2]
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        # only the visible part is scaled, so zooming stays quick on big pictures
        x0, y0 = max(0, int(-self.ox / self.zoom)), max(0, int(-self.oy / self.zoom))
        x1, y1 = min(width, int((cw - self.ox) / self.zoom) + 2), min(height, int((ch - self.oy) / self.zoom) + 2)
        if x1 > x0 and y1 > y0:
            size = (max(1, round((x1 - x0) * self.zoom)), max(1, round((y1 - y0) * self.zoom)))
            method = cv2.INTER_AREA if self.zoom < 1 else cv2.INTER_LINEAR
            self.photo = ImageTk.PhotoImage(Image.fromarray(cv2.resize(self.rgb[y0:y1, x0:x1], size, interpolation=method)))
            canvas.create_image(round(x0 * self.zoom + self.ox), round(y0 * self.zoom + self.oy), image=self.photo, anchor="nw")
        if self.current:
            r = max(3.0, min(12.0, (self.current.diameter or 30) * self.zoom * 0.14))
            for x, y in self.current.points:
                sx, sy = x * self.zoom + self.ox, y * self.zoom + self.oy
                if -r <= sx <= cw + r and -r <= sy <= ch + r:
                    canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill="#ff3b3b", outline="white", width=1)

    def refresh(self):
        picture = self.current
        if picture:
            self.tree.set(str(picture.path), "count", picture.count)
            self.count_label.configure(text=str(picture.count))
            self.detail_label.configure(text=f"found {picture.detected}, you added {picture.added}, removed {picture.removed}")
            self.size_label.configure(text=f"Fruit size: {picture.diameter:.0f} px" if picture.diameter else "Fruit size: -")
        self.total_label.configure(text=str(sum(p.count for p in self.pictures)))
        self.draw()

    # ------------------------------------------------------------ results
    def save(self):
        counted = [p for p in self.pictures if p.done]
        if not counted:
            messagebox.showinfo("Fruit Counter", "Add a picture first.", parent=self.root)
            return
        self.settings["fruit_output"] = self.out_dir.get()
        save_settings(self.settings)
        self.save_btn.configure(state="disabled")
        threading.Thread(target=self.write_results, args=(counted, Path(self.out_dir.get())), daemon=True).start()

    def write_results(self, pictures, folder):
        try:
            workbook_path = write_results(pictures, folder)
            self.root.after(0, self.saved, workbook_path, len(pictures))
        except Exception as e:
            reason = str(e)
            self.root.after(0, lambda: (self.save_btn.configure(state="normal"),
                                        messagebox.showerror("Fruit Counter", f"Could not save:\n{reason}", parent=self.root)))

    def saved(self, workbook_path, n):
        self.save_btn.configure(state="normal")
        messagebox.showinfo("Fruit Counter", f"Saved {workbook_path.name} and {n} marked picture(s) in:\n{workbook_path.parent}", parent=self.root)


def write_results(pictures, folder):
    """An Excel with the counts, and a copy of each picture with its marks numbered. Returns the Excel's path."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = "Counts"
    sheet.append(["Picture", "Count", "Found automatically", "Added by hand", "Removed by hand"])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for picture in pictures:
        sheet.append([picture.path.name, picture.count, picture.detected, picture.added, picture.removed])
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
    for column in "BCDE":
        sheet.column_dimensions[column].width = 18
    return save_workbook(book, folder / "Fruit counts.xlsx")


def open_app(master):
    return FruitCounter(master)

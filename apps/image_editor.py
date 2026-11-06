"""Image Editor: the same edits on many pictures at once, with a live preview. Originals are never touched."""
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk

from . import image_tools as T
from .common import (BORDER, DARK, DND, FG, IMAGE_TYPES, drop_zone, image_files, load_settings,
                     new_window, open_folder, save_settings)


class ImageEditor:
    def __init__(self, master):
        self.root = new_window(master, "Image Editor", (1060, 720), (860, 620))
        self.settings = load_settings()
        self.files = []
        self.preview_source = None          # small copy of the selected picture, for a fast preview
        self.preview_photo = None
        self.after_id = None
        self.problem = ""
        self._vars()
        self._build()

    def _vars(self):
        self.angle = tk.StringVar(value="0")
        self.flip_h, self.flip_v = tk.BooleanVar(), tk.BooleanVar()
        self.ratio = tk.StringVar(value="Keep")
        self.anchor = tk.StringVar(value="Center")
        self.resolution = tk.StringVar(value="Keep")
        self.custom_w, self.custom_h = tk.StringVar(), tk.StringVar()
        self.fit = tk.StringVar(value=T.FIT_MODES[0])
        self.brightness = tk.DoubleVar(value=100)
        self.contrast = tk.DoubleVar(value=100)
        self.saturation = tk.DoubleVar(value=100)
        self.sharpness = tk.DoubleVar(value=100)
        self.format = tk.StringVar(value="Same as original")
        self.quality = tk.IntVar(value=92)
        self.suffix = tk.StringVar(value="_edited")
        self.out_dir = tk.StringVar(value=self.settings.get("images_output", str(Path.home() / "Downloads" / "Images edited")))
        for var in (self.angle, self.flip_h, self.flip_v, self.ratio, self.anchor, self.resolution, self.custom_w,
                    self.custom_h, self.fit, self.brightness, self.contrast, self.saturation, self.sharpness):
            var.trace_add("write", lambda *_: self.schedule_preview())

    # ------------------------------------------------------------ layout
    def _build(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, width=250)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        hint = "Drop pictures or folders here\nor click to choose" if DND else "Click to choose pictures"
        drop_zone(left, hint, self.add, self.choose).pack(fill="x", ipady=16)
        box = ttk.Frame(left)
        box.pack(fill="both", expand=True, pady=8)
        self.listbox = tk.Listbox(box, bg=DARK, fg=FG, selectbackground="#3a5a47", relief="flat", highlightthickness=1,
                                  highlightbackground=BORDER, font=("Segoe UI", 9), activestyle="none", exportselection=False)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.load_preview())
        self.listbox.bind("<Delete>", lambda e: self.remove())
        row = ttk.Frame(left)
        row.pack(fill="x")
        ttk.Button(row, text="Remove", command=self.remove).pack(side="left")
        ttk.Button(row, text="Clear", command=self.clear).pack(side="left", padx=6)
        self.count = ttk.Label(row, text="", style="Muted.TLabel")
        self.count.pack(side="right")

        right = ttk.Frame(main, width=300)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)
        self._controls(right)

        middle = ttk.Frame(main)
        middle.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.canvas = tk.Canvas(middle, bg=DARK, highlightthickness=1, highlightbackground=BORDER)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.schedule_preview())
        self.info = ttk.Label(middle, text="", style="Muted.TLabel")
        self.info.pack(fill="x", pady=(4, 0))

        bottom = ttk.Frame(middle)
        bottom.pack(fill="x", pady=(6, 0))
        self.go_btn = ttk.Button(bottom, text="Save all", style="Go.TButton", command=self.start)
        self.go_btn.pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="determinate", style="Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)
        self.status = ttk.Label(bottom, text="", style="Muted.TLabel", width=20)
        self.status.pack(side="left")

    def _controls(self, parent):
        def head(text):
            ttk.Label(parent, text=text, style="Head.TLabel").pack(anchor="w", pady=(8, 2))

        head("Rotate")
        row = ttk.Frame(parent)
        row.pack(fill="x")
        for text, delta in (("⟲ 90°", -90), ("⟳ 90°", 90), ("180°", 180)):
            ttk.Button(row, text=text, width=6, command=lambda d=delta: self.turn(d)).pack(side="left", padx=(0, 3))
        ttk.Entry(row, textvariable=self.angle, width=5).pack(side="left", padx=(6, 2))
        ttk.Label(row, text="°").pack(side="left")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(row, text="Mirror", variable=self.flip_h).pack(side="left")
        ttk.Checkbutton(row, text="Upside down", variable=self.flip_v).pack(side="left", padx=10)

        head("Cut to a shape")
        self._combo(parent, "Ratio", self.ratio, list(T.RATIOS))
        self._combo(parent, "Keep", self.anchor, list(T.ANCHORS))

        head("Resolution")
        self._combo(parent, "Size", self.resolution, list(T.RESOLUTIONS) + ["Custom"])
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Custom", width=7).pack(side="left")
        ttk.Entry(row, textvariable=self.custom_w, width=7).pack(side="left")
        ttk.Label(row, text=" x ").pack(side="left")
        ttk.Entry(row, textvariable=self.custom_h, width=7).pack(side="left")
        self._combo(parent, "How", self.fit, list(T.FIT_MODES))

        head("Adjust")
        for text, var in (("Brightness", self.brightness), ("Contrast", self.contrast),
                          ("Colour", self.saturation), ("Sharpness", self.sharpness)):
            self._slider(parent, text, var)
        ttk.Button(parent, text="Reset all edits", command=self.reset).pack(anchor="w", pady=(4, 0))

        head("Save as")
        self._combo(parent, "Format", self.format, list(T.FORMATS))
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Quality", width=7).pack(side="left")
        ttk.Scale(row, from_=40, to=100, variable=self.quality, orient="horizontal").pack(side="left", fill="x", expand=True)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Add to name", width=11).pack(side="left")
        ttk.Entry(row, textvariable=self.suffix, width=12).pack(side="left")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Entry(row, textvariable=self.out_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="...", width=3, command=self.choose_out).pack(side="left", padx=(3, 0))
        ttk.Button(row, text="Open", width=5, command=lambda: open_folder(self.out_dir.get())).pack(side="left", padx=(3, 0))

    def _combo(self, parent, text, var, values):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=text, width=7).pack(side="left")
        ttk.Combobox(row, textvariable=var, values=values, state="readonly").pack(side="left", fill="x", expand=True)

    def _slider(self, parent, text, var):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)
        ttk.Label(row, text=text, width=10).pack(side="left")
        value = ttk.Label(row, text="100%", width=5, style="Muted.TLabel")
        value.pack(side="right")
        ttk.Scale(row, from_=0, to=200, variable=var, orient="horizontal").pack(side="left", fill="x", expand=True)
        var.trace_add("write", lambda *_: value.configure(text=f"{var.get():.0f}%"))

    # ------------------------------------------------------------ files
    def choose(self):
        types = " ".join(f"*{e}" for e in IMAGE_TYPES)
        paths = filedialog.askopenfilenames(parent=self.root, title="Choose pictures", filetypes=[("Pictures", types), ("All files", "*.*")])
        if paths:
            self.add(paths)

    def add(self, paths):
        was_empty = not self.files
        for f in image_files(paths):
            if f not in self.files:
                self.files.append(f)
                self.listbox.insert("end", f.name)
        self.count.configure(text=str(len(self.files)))
        if was_empty and self.files:
            self.listbox.selection_set(0)
            self.load_preview()

    def remove(self):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            del self.files[i]
        self.count.configure(text=str(len(self.files)) if self.files else "")
        if self.files:
            self.listbox.selection_set(0)
        self.load_preview()

    def clear(self):
        self.listbox.delete(0, "end")
        self.files = []
        self.count.configure(text="")
        self.load_preview()

    def choose_out(self):
        d = filedialog.askdirectory(parent=self.root, title="Where to save the edited pictures", initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    # ------------------------------------------------------------ recipe
    def turn(self, delta):
        try:
            current = float(self.angle.get() or 0)
        except ValueError:
            current = 0
        self.angle.set(f"{(current + delta) % 360:g}")

    def reset(self):
        self.angle.set("0")
        self.flip_h.set(False)
        self.flip_v.set(False)
        self.ratio.set("Keep")
        self.anchor.set("Center")
        self.resolution.set("Keep")
        self.custom_w.set("")
        self.custom_h.set("")
        self.fit.set(T.FIT_MODES[0])
        for var in (self.brightness, self.contrast, self.saturation, self.sharpness):
            var.set(100)

    def size(self):
        name = self.resolution.get()
        if name != "Custom":
            return T.RESOLUTIONS.get(name)
        try:
            w, h = int(self.custom_w.get()), int(self.custom_h.get())
        except ValueError:
            return None
        return (w, h) if w > 0 and h > 0 else None

    def recipe(self):
        try:
            angle = float(self.angle.get() or 0)
        except ValueError:
            angle = 0
        return T.Recipe(angle=angle, flip_h=self.flip_h.get(), flip_v=self.flip_v.get(), ratio=T.RATIOS.get(self.ratio.get()),
                        anchor=self.anchor.get(), size=self.size(), fit=self.fit.get(),
                        brightness=self.brightness.get() / 100, contrast=self.contrast.get() / 100,
                        saturation=self.saturation.get() / 100, sharpness=self.sharpness.get() / 100)

    # ------------------------------------------------------------ preview
    def load_preview(self):
        self.preview_source = None
        self.problem = ""
        selected = self.listbox.curselection()
        if selected:
            try:
                with Image.open(self.files[selected[0]]) as img:
                    w, h = img.size
                    self.original_size = (h, w) if img.getexif().get(274) in (5, 6, 7, 8) else (w, h)   # phone pictures
                    img.draft("RGB", (1400, 1400))
                    self.preview_source = ImageOps.exif_transpose(img)
                    self.preview_source.thumbnail((1400, 1400))
            except Exception as e:
                self.problem = f"Can't open this picture: {e}"
        self.schedule_preview()

    def schedule_preview(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.after_id = self.root.after(80, self.draw_preview)     # wait for the slider to pause

    def draw_preview(self):
        self.after_id = None
        self.canvas.delete("all")
        if self.preview_source is None:
            self.info.configure(text=self.problem)
            return
        recipe = self.recipe()
        final = T.result_size(self.original_size, recipe)
        if recipe.size and max(recipe.size) > 1000:      # only the shape matters for a preview: keep it fast
            scale = 1000 / max(recipe.size)
            recipe = replace(recipe, size=(max(1, round(recipe.size[0] * scale)), max(1, round(recipe.size[1] * scale))))
        try:
            result = T.apply(self.preview_source, recipe)
        except Exception as e:
            self.info.configure(text=f"Can't apply these edits: {e}")
            return
        cw, ch = max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)
        result.thumbnail((cw - 10, ch - 10))
        self.preview_photo = ImageTk.PhotoImage(result)
        self.canvas.create_image(cw // 2, ch // 2, image=self.preview_photo)
        self.info.configure(text=f"Preview of the selected picture. Original {self.original_size[0]} x {self.original_size[1]}"
                                 f"  ->  result {final[0]} x {final[1]}")

    # ------------------------------------------------------------ save
    def start(self):
        if not self.files:
            messagebox.showinfo("Image Editor", "Add some pictures first.", parent=self.root)
            return
        self.settings["images_output"] = self.out_dir.get()
        save_settings(self.settings)
        self.go_btn.configure(state="disabled")
        args = (list(self.files), Path(self.out_dir.get()), self.recipe(), self.suffix.get(),
                T.FORMATS[self.format.get()], int(self.quality.get()))
        threading.Thread(target=self.work, args=args, daemon=True).start()

    def work(self, files, out_dir, recipe, suffix, extension, quality):
        def progress(i, n, name):
            self.root.after(0, lambda: (self.progress.configure(maximum=n, value=i),
                                        self.status.configure(text=name[:24] if name else "")))
        try:
            saved, failed = T.process_batch(files, out_dir, recipe, suffix, extension, quality, progress)
            self.root.after(0, self.done, saved, failed, out_dir)
        except Exception as e:
            self.root.after(0, self.failed, e)

    def failed(self, e):
        self.go_btn.configure(state="normal")
        self.status.configure(text="Failed")
        messagebox.showerror("Image Editor", f"The pictures could not be saved:\n{e}\n\nTry another output folder.", parent=self.root)

    def done(self, saved, failed, out_dir):
        self.go_btn.configure(state="normal")
        self.status.configure(text=f"Saved {len(saved)}")
        message = f"{len(saved)} picture(s) saved in:\n{out_dir}\n\nThe originals weren't changed."
        if failed:
            message += "\n\nCould not edit:\n" + "\n".join(f"  {n}: {e}" for n, e in failed[:15])
            messagebox.showwarning("Image Editor", message, parent=self.root)
        else:
            messagebox.showinfo("Image Editor", message, parent=self.root)


def open_app(master):
    return ImageEditor(master)

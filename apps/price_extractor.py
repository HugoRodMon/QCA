"""Price Extractor (Europe): daily supplier price lists -> Excel, in the final files' columns."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pricex.base import suppliers
from pricex.extractor import name_hint
from pricex.output import OutputFolderError
from pricex.pipeline import SUPPORTED, run

from .common import DND, FG, drop_zone, load_settings, new_window, open_folder, save_settings


class App:
    def __init__(self, master):
        self.root = new_window(master, "Price Extractor - Europe", (900, 640), (700, 500))
        self.settings = load_settings()
        self.files = []                          # [Path]
        self.out_dir = tk.StringVar(value=self.settings.get("output", str(Path.home() / "Downloads" / "Prices extracted")))
        self._build()

    def _build(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        hint = "Drop price files here (pdf, txt, mhtml, xlsx, pictures)  -  or click to choose" if DND else "Click to choose price files"
        self.drop = drop_zone(main, hint, self.add, self.choose_files)
        self.drop.pack(fill="x", ipady=22)

        table = ttk.Frame(main)
        table.pack(fill="both", expand=True, pady=(12, 6))
        self.tree = ttk.Treeview(table, columns=("supplier", "file"), show="headings", selectmode="extended")
        self.tree.heading("supplier", text="Supplier")
        self.tree.heading("file", text="File")
        self.tree.column("supplier", width=170, stretch=False)
        self.tree.column("file", width=600)
        sb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Delete>", lambda e: self.remove_selected())

        row = ttk.Frame(main)
        row.pack(fill="x", pady=(0, 8))
        ttk.Button(row, text="Add files", command=self.choose_files).pack(side="left")
        ttk.Button(row, text="Remove selected", command=self.remove_selected).pack(side="left", padx=6)
        ttk.Button(row, text="Clear", command=self.clear).pack(side="left")
        self.count = ttk.Label(row, text="", style="Muted.TLabel")
        self.count.pack(side="right")

        out = ttk.Frame(main)
        out.pack(fill="x", pady=(4, 8))
        ttk.Label(out, text="Save to:").pack(side="left")
        ttk.Entry(out, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(out, text="Change", command=self.choose_out).pack(side="left")
        ttk.Button(out, text="Open folder", command=self.open_out).pack(side="left", padx=(6, 0))

        go = ttk.Frame(main)
        go.pack(fill="x", pady=(4, 8))
        self.go_btn = ttk.Button(go, text="Extract prices", style="Go.TButton", command=self.start)
        self.go_btn.pack(side="left")
        self.progress = ttk.Progressbar(go, mode="determinate", style="Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)
        self.status = ttk.Label(go, text="", style="Muted.TLabel", width=34)
        self.status.pack(side="left")

        self.log = tk.Text(main, height=11, bg="#18191d", fg=FG, insertbackground=FG, relief="flat",
                           font=("Consolas", 9), wrap="none")
        self.log.pack(fill="both", expand=False)
        self.log.tag_configure("head", foreground="#e8c26b", font=("Consolas", 9, "bold"))
        self.log.tag_configure("bad", foreground="#e57373")

    # ------------------------------------------------------------ files
    def choose_files(self):
        start = self.settings.get("input", str(Path.home() / "Downloads"))
        paths = filedialog.askopenfilenames(
            parent=self.root, title="Choose price files", initialdir=start,
            filetypes=[("Price files", " ".join(f"*{e}" for e in sorted(SUPPORTED))), ("All files", "*.*")])
        if paths:
            self.settings["input"] = str(Path(paths[0]).parent)
            save_settings(self.settings)
            self.add(paths)

    def add(self, paths):
        finals = {s.final_file.lower() for s in suppliers() if s.final_file}
        left_out = 0
        for p in paths:
            p = Path(p)
            items = sorted(f for f in p.iterdir() if f.suffix.lower() in SUPPORTED) if p.is_dir() else [p]
            for f in items:
                if f in self.files:
                    continue
                if f.name.lower() in finals:              # a final (OneDrive) Excel, not a price list
                    left_out += 1
                    continue
                self.files.append(f)
                sup = name_hint(f)              # a first guess; the content decides when extracting
                self.tree.insert("", "end", iid=str(f),
                                 values=(f"{sup.name} (name)" if sup else "? (read when extracting)", f.name))
        note = f"   ({left_out} final Excel file(s) left out)" if left_out else ""
        self.count.configure(text=f"{len(self.files)} file(s){note}")

    def remove_selected(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.files = [f for f in self.files if str(f) != iid]
        self.count.configure(text=f"{len(self.files)} file(s)" if self.files else "")

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.files = []
        self.count.configure(text="")

    def choose_out(self):
        d = filedialog.askdirectory(parent=self.root, title="Where to save the extracted prices", initialdir=self.out_dir.get())
        if d:
            self.out_dir.set(d)

    def open_out(self):
        open_folder(self.out_dir.get())

    # ------------------------------------------------------------ run
    def start(self):
        if not self.files:
            messagebox.showinfo("Price Extractor", parent=self.root, message="Add some price files first.")
            return
        self.settings["output"] = self.out_dir.get()
        save_settings(self.settings)
        self.go_btn.configure(state="disabled")
        self.log.delete("1.0", "end")
        threading.Thread(target=self.work, args=(list(self.files), Path(self.out_dir.get())), daemon=True).start()

    def work(self, files, out_dir):
        def progress(i, n, name):
            self.root.after(0, self.show_progress, i, n, name)
        try:
            report = run(files, out_dir, progress)
            self.root.after(0, self.done, report)
        except Exception as e:                                         # never leave the window stuck
            self.root.after(0, self.failed, e)

    def show_progress(self, i, n, name):
        self.progress.configure(maximum=n, value=i)
        self.status.configure(text=f"Reading {name}" if name else "Writing Excel...")

    def failed(self, e):
        self.go_btn.configure(state="normal")
        self.status.configure(text="Failed")
        if isinstance(e, OutputFolderError):
            messagebox.showerror("Can't save in this folder", str(e), parent=self.root)
        elif isinstance(e, PermissionError):
            messagebox.showerror("Price Extractor", parent=self.root, message=f"Windows refused access to a file:\n{e}\n\n"
                                 "If it's one of the price Excel files, close it in Excel and try again.")
        else:
            messagebox.showerror("Price Extractor", parent=self.root, message=f"Something went wrong:\n{e}")

    def done(self, report):
        self.go_btn.configure(state="normal")
        rows = sum(len(r.rows) for r in report.results)
        self.status.configure(text=f"Done: {rows} prices")
        # show which supplier each file really is (read from its content)
        for f in self.files:
            res = next((r for r in report.results if r.file == f.name), None)
            if res:
                self.tree.set(str(f), "supplier", res.supplier + ("" if res.identified_by.startswith("file name") else " ✓"))
            elif any(e.startswith(f.name) for e in report.errors):
                self.tree.set(str(f), "supplier", "NOT RECOGNISED")
        for line in report.text().splitlines():
            tag = "head" if line and not line.startswith(" ") else None
            if line.startswith("NOT PROCESSED") or line.startswith("WARNINGS"):
                tag = "bad"
            self.log.insert("end", line + "\n", tag)

        msg = []
        if report.renamed:
            msg.append("These files are open (probably in Excel), so the new prices were saved as:\n" +
                       "\n".join(f"   {used}" for _, used in report.renamed))
        if report.combined:
            msg.append(f"Combined file:\n   {report.combined.name}")
        if report.separate:
            msg.append("Separate files (their final file is split by species):\n" +
                       "\n".join(f"   {p.name}" for _, p in report.separate))
        if report.errors:
            msg.append(f"{len(report.errors)} file(s) could not be processed - see the log.")
        skipped = sum(len(r.skipped) for r in report.results)
        if skipped:
            msg.append(f"{skipped} price(s) of unknown products were not extracted - see the log.")
        title = "Extraction finished"
        if report.errors:
            messagebox.showwarning(title, parent=self.root, message="\n\n".join(msg) or "Nothing extracted.")
        else:
            messagebox.showinfo(title, parent=self.root, message="\n\n".join(msg) or "Nothing extracted.")


def open_app(master):
    return App(master)


def run_without_window(args):
    """DQSApps.exe --extract <files or folders> -o <output folder>   (writes report.txt there)"""
    out = Path(args[args.index("-o") + 1]) if "-o" in args else Path.cwd() / "Prices extracted"
    inputs = [Path(a) for a in args if a not in ("--extract", "-o") and Path(a) != out]
    files = []
    for p in inputs:
        files += sorted(f for f in p.iterdir() if f.suffix.lower() in SUPPORTED) if p.is_dir() else [p]
    report = run(files, out)
    out.mkdir(parents=True, exist_ok=True)
    return report, out

# PyInstaller recipe for DQSApps.exe  ->  pyinstaller DQSApps.spec
# (the GitHub Action runs this; you only need it to build locally)
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas = [("pricex/data", "pricex/data"),
         ("apps/locked", "apps/locked")]        # the private apps, encrypted
binaries = []
# supplier parsers are found at run time, so PyInstaller has to be told about them.
# Listed from the folder (collect_submodules finds nothing when run as `pyinstaller` instead of `python -m`).
hiddenimports = ["pricex.suppliers." + f.stem for f in sorted(Path("pricex/suppliers").glob("*.py"))
                 if f.stem != "__init__"]
# what the private apps use: PyInstaller can't see inside the encrypted bundle
hiddenimports += ["uuid", "pdfplumber", "openpyxl.styles", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox"]
for pkg in ("tkinterdnd2", "pypdfium2", "pypdfium2_raw",
            "rapidocr_onnxruntime",                       # OCR for pictures: models + config
            "winrt"):                                     # Windows' own OCR
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["dqs.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # big libraries installed on the build machine that the app never uses
    excludes=["pandas", "matplotlib", "camelot", "tabula", "fitz", "pymupdf", "IPython", "notebook",
              "scipy", "lxml", "pytest", "setuptools", "torch", "tensorflow"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DQSApps",
    console=False,          # a window app, no black console
    upx=False,              # UPX-packed exes trigger antivirus false alarms
    icon=None,
)

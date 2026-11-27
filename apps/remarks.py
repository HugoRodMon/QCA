"""Remarks: paste an inspection report, pick the client, copy the remark.

The pasted report is read and kept only while the app is open (nothing is written to the PC). The templates
come, newest first, from:
  1. the shared copy on the team's Google Drive (remarks/remark templates.json), which everyone reads: through
     its "anyone with the link" address (SHARED_ID below), no key needed;
  2. the last shared copy this PC downloaded (%APPDATA%, for when there's no internet);
  3. the ones that come with the app (remarks/data/templates.json).
Changing the shared copy (everyone's default) needs the templates key: it opens locked/remarks.enc, the Drive
service account (tools/lock_remarks.py makes it). Without it, edits are only for the remark on screen.
"""
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

from remarks import headers, render, report as R

from .common import SETTINGS, load_settings, remember
from .locked import unlock

BUILT_IN = Path(__file__).resolve().parents[1] / "remarks" / "data" / "templates.json"
CACHE = SETTINGS.parent / "remark templates.json"
BUNDLE = Path(__file__).parent / "locked" / "remarks.enc"
FOLDER, NAME = "remarks", "remark templates.json"
# the shared file's id on Drive, readable by anyone with the link (set once the file is made: see the README)
SHARED_ID = "1PhIxB1_iP_oSrfRwZsUp_EmnMo4VIyRG"
PUBLIC_URL = "https://drive.google.com/uc?export=download&id={}"


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


class Api:
    def __init__(self, host):
        self._host = host
        self._report = None
        self._lock = threading.Lock()
        built_in = _read_json(BUILT_IN) or {"templates": []}
        cached = _read_json(CACHE)
        self._shared = cached if cached and cached.get("templates") else None
        self._built_in = built_in
        self._status = "from this PC's last copy" if self._shared else "the app's own"

    # ---------------------------------------------------------------- templates
    @property
    def _templates(self):
        return (self._shared or self._built_in)["templates"]

    def _layouts(self):
        shared = (self._shared or {}).get("layouts", {})
        return {**shared, **load_settings().get("remark_layouts", {})}

    def state(self):
        threading.Thread(target=self._refresh, daemon=True).start()
        return self._state()

    def _state(self):
        clients = sorted({t["client"] for t in self._templates if t.get("client") not in ("*", "")})
        data = self._shared or self._built_in
        meaning = data.get("meaning", {})                # the admin's descriptions of the built-in ones
        holders = {k: meaning.get(k, v) for k, v in render.PLACEHOLDERS.items()}
        custom = data.get("custom", {})                  # the admin's own: {name: {"text", "help"}}
        holders.update({k: c.get("help") or c.get("text", "") for k, c in custom.items()})
        return {"clients": clients, "editor": self._editor() is not None, "source": self._status,
                "saved": data.get("saved", ""), "placeholders": holders,
                "box_placeholders": {k: meaning.get(k, v) for k, v in render.BOX_PLACEHOLDERS.items()},
                "built_in": render.PLACEHOLDERS, "built_in_box": render.BOX_PLACEHOLDERS,
                "meaning": meaning, "custom": custom, "phrases": data.get("phrases", []), "groups": self._groups()}

    def _groups(self):
        """Which defects are Quality and which Condition: everyone's (shared) with this PC's changes on top.
        {defect name (lowercase): 'quality' | 'condition'}; '' on this PC takes one out of the shared groups."""
        merged = dict((self._shared or self._built_in).get("defect_groups", {}))
        merged.update(load_settings().get("remark_groups", {}))
        return {k: v for k, v in merged.items() if v in render.GROUPS}

    def set_group(self, defect, group):
        """Put a defect in the Quality or Condition group ('' = none), on this PC."""
        local = load_settings().get("remark_groups", {})
        local[str(defect).strip().lower()] = group if group in render.GROUPS else ""
        remember("remark_groups", local)
        return self._groups()

    def save_groups(self):
        """This PC's groups become everyone's. Needs the templates key."""
        groups = self._groups()

        def change(data):
            data["defect_groups"] = groups
        result = self._publish(change)
        if result.get("ok"):
            remember("remark_groups", {})                # now part of everyone's
        return result

    def _custom(self):
        return {k: c.get("text", "") for k, c in (self._shared or self._built_in).get("custom", {}).items()}

    def _refresh(self):
        """Download the shared templates (in the background when the app opens)."""
        data = None
        if SHARED_ID:
            try:
                with urllib.request.urlopen(PUBLIC_URL.format(SHARED_ID), timeout=15) as r:
                    data = json.loads(r.read())
            except Exception:
                data = None
        if data is None and self._editor():
            try:
                drive, file_id = self._drive()
                data = json.loads(drive.download(file_id)) if file_id else None
            except Exception:
                data = None
        if data and data.get("templates"):
            with self._lock:
                self._shared = data
                self._status = "shared"
            try:
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
            self._host.emit("remarks.templates", self._state())

    def template(self, client, product):
        t = render.pick(self._templates, client, product)
        default = render.pick(self._templates, "*", "*")
        return {"client": t.get("client"), "product": t.get("product"), "remark": t.get("remark", ""),
                "box": t.get("box", ""), "own": t is not default}

    # ---------------------------------------------------------------- the report
    def read(self, grid):
        """The pasted grid -> what the screen shows. Column names written as pictures are read here."""
        self._report = R.read(grid, headers.name_of, self._layouts())
        if all(self._report.columns) and self._report.template_name:
            self._remember_layout()
        return self._view()

    def set_summary(self, label, value):
        """A summary value corrected by hand (Inspection Date, Place, Origin...): for this report only."""
        if self._report:
            self._report.summary[str(label)] = " ".join(str(value or "").split())
        return self._view()

    def name_column(self, i, name):
        """A column name typed in by hand (a picture that couldn't be read)."""
        r = self._report
        name = (name or "").strip()
        r.columns[i] = (R.snap(name) or name) if name else None
        R.fill(r)
        if all(r.columns) and r.template_name:
            self._remember_layout()
        return self._view()

    def _remember_layout(self):
        layouts = load_settings().get("remark_layouts", {})
        layouts[self._report.template_name] = self._report.columns
        remember("remark_layouts", layouts)

    def clear(self):
        self._report = None

    def _view(self):
        r = self._report
        shown = lambda v: render.number(float(v)) + "%" if isinstance(v, R.Percent) else str(v)   # noqa: E731
        return {
            "summary": r.summary, "columns": r.columns, "problems": r.problems,
            "boxes": [[shown(b.get(c, "")) if c else raw for c, raw in zip(r.columns, row)]
                      for b, row in zip(r.boxes, r.raw)],
            "defects": [{"name": n, "avg": render.number(a), "boxes": k, "all": render.number(t)} for n, a, k, t in r.defects],
            "client": r.summary.get("Business partner", ""), "product": str(r.first("Product")),
            "template_name": r.template_name,
        }

    def render(self, client, product, remark, box, chosen):
        if not self._report:
            return {"text": "", "boxes": [], "unknown": [], "values": {}}
        t = render.pick(self._templates, client, product)
        return render.render(t, self._report, remark, box, set(chosen) if chosen is not None else None, self._custom(),
                             self._groups())

    # ---------------------------------------------------------------- everyone's defaults (templates key)
    def _editor(self, key=None):
        key = key if key is not None else load_settings().get("remarks_key")
        return unlock(key.strip(), BUNDLE) if key and key.strip() else None

    def editor_key(self, key):
        """Remember the templates key if it's right. Returns the new state, or None."""
        if not self._editor(key):
            return None
        remember("remarks_key", key.strip())
        return self._state()

    def _drive(self):
        from .gdrive import Drive
        opened = self._editor()
        drive = Drive(opened["key"])
        file_id = opened.get("file") or SHARED_ID
        if not file_id:
            folder = drive.folder(opened["drive"], FOLDER)
            found = drive.list(folder, f"name = '{NAME}'")
            file_id = found[0]["id"] if found else None
        return drive, file_id

    def save_default(self, client, product, remark, box):
        """Make this the template for everyone (client / product, '*' = any). Needs the templates key."""
        def change(data):
            self._put_template(data, client, product, remark, box)
        return self._publish(change)

    def save_placeholders(self, meaning, custom):
        """Everyone's placeholder descriptions and the admin's own placeholders. Needs the templates key.
        meaning: {built-in name: description}; custom: {name: {"text": ..., "help": ...}}."""
        known = set(render.PLACEHOLDERS) | set(render.BOX_PLACEHOLDERS)
        clean = {}
        for name, c in (custom or {}).items():
            key = " ".join(str(name).replace("[", " ").replace("]", " ").split()).lower()
            if key and key not in known and str(c.get("text", "")).strip():
                clean[key] = {"text": str(c["text"]).strip(), "help": str(c.get("help", "")).strip()}

        def change(data):
            data["meaning"] = {k: str(v).strip() for k, v in (meaning or {}).items()
                               if k in known and str(v).strip() and str(v).strip() != {**render.PLACEHOLDERS, **render.BOX_PLACEHOLDERS}[k]}
            data["custom"] = clean
        return self._publish(change)

    def save_phrases(self, phrases):
        """Everyone's ready-made phrases (inserted into a template with a click). Needs the templates key."""
        clean = []
        for p in phrases or []:
            text = " ".join(str(p).split())
            if text and text not in clean:
                clean.append(text)

        def change(data):
            data["phrases"] = clean
        return self._publish(change)

    def _put_template(self, data, client, product, remark, box):
        templates = data.setdefault("templates", [])
        same = lambda t: (t.get("client", "").lower(), t.get("product", "").lower()) == (client.lower(), product.lower())  # noqa: E731
        existing = next((t for t in templates if same(t)), None)
        if existing:
            existing.update(remark=remark, box=box)
        else:
            # a new client/product keeps the rules (categories, grade) of the template it started from
            base = render.pick(templates, client, product)
            new = {k: v for k, v in base.items() if k not in ("client", "product", "remark", "box")}
            templates.append({"client": client, "product": product, "remark": remark, "box": box, **new})

    def _publish(self, change):
        """Change everyone's copy and put it on Drive."""
        if not self._editor():
            return {"ok": False, "error": "This PC doesn't have the templates key."}
        with self._lock:
            data = json.loads(json.dumps(self._shared or self._built_in))
        change(data)
        data["layouts"] = {**data.get("layouts", {}), **load_settings().get("remark_layouts", {})}
        data["saved"] = time.strftime("%Y-%m-%d %H:%M")
        data["by"] = os.environ.get("COMPUTERNAME", "")
        body = json.dumps(data, indent=1, ensure_ascii=False).encode("utf-8")
        try:
            drive, file_id = self._drive()
            if file_id:
                drive.replace(file_id, body, "application/json")
            else:
                drive.upload(drive.folder(self._editor()["drive"], FOLDER), NAME, body, "application/json")
        except Exception as e:
            return {"ok": False, "error": f"Couldn't save to Google Drive: {e}"}
        with self._lock:
            self._shared, self._status = data, "shared"
        try:
            CACHE.write_text(body.decode("utf-8"), encoding="utf-8")
        except OSError:
            pass
        return {"ok": True, "state": self._state()}

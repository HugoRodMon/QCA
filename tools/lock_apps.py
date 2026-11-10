"""Encrypt the private apps (private_apps/*.py) into apps/locked/apps.enc, the only part that's published.

    python tools/lock_apps.py                 uses the key in private_apps/KEY.txt
    python tools/lock_apps.py --new-key       makes a new random key, saves it in KEY.txt and locks with it

Run it after changing a private app or the key, commit apps/locked/apps.enc and publish a version.
private_apps/ is ignored by git: keep a safe copy of it, the source can't be recovered from GitHub
without the key. If the key changes, everybody who has access needs the new one.
"""
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.locked import BUNDLE, lock, unlock  # noqa: E402

PRIVATE = ROOT / "private_apps"
KEY_FILE = PRIVATE / "KEY.txt"
APPS = [
    {"id": "invoice_to_excel", "code": "IX", "title": "Invoices to Excel", "description": "PDF invoices → Excel"},
    {"id": "file_renamer", "code": "FR", "title": "File Renamer", "description": "Number files in order"},
]
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # 32 signs, without the look-alikes 0/O and 1/I

if "--new-key" in sys.argv or not KEY_FILE.exists():
    # 16 signs = 80 bits: the encrypted file is public, so the key must resist automated guessing
    key = "-".join("".join(secrets.choice(LETTERS) for _ in range(4)) for _ in range(4))
    KEY_FILE.write_text(key, encoding="utf-8")
    print(f"New key saved in {KEY_FILE}")
key = KEY_FILE.read_text(encoding="utf-8").strip()

bundle = [dict(app, source=(PRIVATE / f"{app['id']}.py").read_text(encoding="utf-8")) for app in APPS]
BUNDLE.parent.mkdir(parents=True, exist_ok=True)
BUNDLE.write_bytes(lock(bundle, key))

assert [a["id"] for a in unlock(key)] == [a["id"] for a in APPS]
assert unlock(key + "x") is None
print(f"Locked {len(bundle)} apps into {BUNDLE} ({BUNDLE.stat().st_size} bytes). Key check OK.")

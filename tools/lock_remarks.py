"""Encrypt the Google service account key for the Remarks app's shared templates into apps/locked/remarks.enc.

    python tools/lock_remarks.py <service-account.json> <shared drive id> [<templates file id>]
    python tools/lock_remarks.py <service-account.json> <shared drive id> [<templates file id>] --new-key

The templates key that opens it is in private_apps/TEMPLATES_KEY.txt (made the first time, or with --new-key):
give it only to the people who may change everyone's remark templates. Commit apps/locked/remarks.enc and
publish a version. Never commit the .json key itself.
"""
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.locked import lock, unlock  # noqa: E402
from apps.remarks import BUNDLE  # noqa: E402

KEY_FILE = ROOT / "private_apps" / "TEMPLATES_KEY.txt"
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # 32 signs, without the look-alikes 0/O and 1/I

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) not in (2, 3):
    sys.exit(__doc__)
account = json.loads(Path(args[0]).read_text(encoding="utf-8"))
if account.get("type") != "service_account" or "private_key" not in account:
    sys.exit("That isn't a service account key (.json downloaded from Google Cloud).")

if "--new-key" in sys.argv or not KEY_FILE.exists():
    # 16 signs = 80 bits: remarks.enc is public, so the key must resist automated guessing
    KEY_FILE.parent.mkdir(exist_ok=True)
    KEY_FILE.write_text("-".join("".join(secrets.choice(LETTERS) for _ in range(4)) for _ in range(4)), encoding="utf-8")
    print(f"New templates key saved in {KEY_FILE}")
key = KEY_FILE.read_text(encoding="utf-8").strip()

content = {"key": account, "drive": args[1]}
if len(args) == 3:
    content["file"] = args[2]
BUNDLE.parent.mkdir(parents=True, exist_ok=True)
BUNDLE.write_bytes(lock(content, key))
assert unlock(key, BUNDLE)["drive"] == args[1]
assert unlock(key + "x", BUNDLE) is None
print(f"Locked {account['client_email']} and drive {args[1]} into {BUNDLE}. Key check OK.")

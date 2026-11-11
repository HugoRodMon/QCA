"""Encrypt the Google service account key for the Fruit Counter lessons into apps/locked/lessons.enc.

    python tools/lock_lessons.py <service-account.json> <shared drive id>
    python tools/lock_lessons.py <service-account.json> <shared drive id> --new-key

The team key that opens it is in private_apps/TEAM_KEY.txt (made the first time, or with --new-key): give it to
the team, they type it once in the Fruit Counter. Commit apps/locked/lessons.enc and publish a version.
Never commit the .json key itself. If the team key changes, every PC needs the new one.
"""
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.lessons import BUNDLE  # noqa: E402
from apps.locked import lock, unlock  # noqa: E402

KEY_FILE = ROOT / "private_apps" / "TEAM_KEY.txt"
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # 32 signs, without the look-alikes 0/O and 1/I

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) != 2:
    sys.exit(__doc__)
account = json.loads(Path(args[0]).read_text(encoding="utf-8"))
if account.get("type") != "service_account" or "private_key" not in account:
    sys.exit("That isn't a service account key (.json downloaded from Google Cloud).")

if "--new-key" in sys.argv or not KEY_FILE.exists():
    # 16 signs = 80 bits: lessons.enc is public, so the key must resist automated guessing
    KEY_FILE.parent.mkdir(exist_ok=True)
    KEY_FILE.write_text("-".join("".join(secrets.choice(LETTERS) for _ in range(4)) for _ in range(4)), encoding="utf-8")
    print(f"New team key saved in {KEY_FILE}")
team_key = KEY_FILE.read_text(encoding="utf-8").strip()

BUNDLE.parent.mkdir(parents=True, exist_ok=True)
BUNDLE.write_bytes(lock({"key": account, "drive": args[1]}, team_key))
assert unlock(team_key, BUNDLE)["drive"] == args[1]
assert unlock(team_key + "x", BUNDLE) is None
print(f"Locked {account['client_email']} and drive {args[1]} into {BUNDLE}. Key check OK.")

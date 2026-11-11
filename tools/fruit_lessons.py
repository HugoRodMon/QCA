"""Download the Fruit Counter lessons from the team's Google Drive, to tune the counter on.

    python tools/fruit_lessons.py [folder]          (default: fruit_lessons/ next to this project)

Only new lessons are downloaded. Each is a picture and a .json: "found" is what the counter marked, "final" what
the person corrected it to (the right answer), with the count mode, the measured fruit and the slider setting.
Uses the team key in private_apps/TEAM_KEY.txt.
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.gdrive import FOLDER, Drive  # noqa: E402
from apps.lessons import access  # noqa: E402

target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "fruit_lessons"
opened = access((ROOT / "private_apps" / "TEAM_KEY.txt").read_text(encoding="utf-8").strip())
if not opened:
    sys.exit("The team key in private_apps/TEAM_KEY.txt doesn't open apps/locked/lessons.enc.")
drive = Drive(opened["key"])
root = [f for f in drive.list(opened["drive"], f"name = 'lessons' and mimeType = '{FOLDER}'")]
if not root:
    sys.exit("No lessons yet.")
target.mkdir(parents=True, exist_ok=True)
new, months = 0, Counter()
for month in sorted(drive.list(root[0]["id"], f"mimeType = '{FOLDER}'"), key=lambda f: f["name"]):
    for f in drive.list(month["id"]):
        months[month["name"]] += f["name"].endswith(".json")
        path = target / f["name"]
        if not path.exists():
            path.write_bytes(drive.download(f["id"]))
            new += 1
print(f"{new} new files in {target}")
print("Lessons per month:", ", ".join(f"{m}: {n}" for m, n in sorted(months.items())) or "-")

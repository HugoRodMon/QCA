"""Fruit Counter lessons: corrected counts sent to the team's Google Drive, to tune the counter on.

When someone saves counts they checked, each picture becomes a lesson: a smaller copy of the picture plus what
the counter found and what the person corrected it to. Lessons wait in a local queue (%APPDATA%) and go up in the
background, so saving never waits on the internet; whatever can't be sent stays queued for the next start.

They go to a shared drive through a Google service account. Its key is in locked/lessons.enc, encrypted with the
team key (typed once per PC); tools/lock_lessons.py makes that file. The account is only a Contributor on that
shared drive: it can add lessons, and can't delete anything.
"""
import io
import json
import os
import threading
import time
import uuid
from pathlib import Path

from .common import SETTINGS, load_settings, remember
from .locked import unlock

BUNDLE = Path(__file__).parent / "locked" / "lessons.enc"
QUEUE = SETTINGS.parent / "lessons"
SIDE = 1600             # pictures are sent at most this big (a few hundred KB)

_lock = threading.Lock()
_access = None          # {"key": service account, "drive": shared drive id}, once the team key has opened it
_uploading = False


def access(team_key=None):
    """What the team key opens, or None. Without a key, the one remembered on this PC."""
    global _access
    if team_key is None:
        if _access is not None:
            return _access
        team_key = load_settings().get("team_key")
        if not team_key:
            return None
    opened = unlock(team_key.strip(), BUNDLE)
    if opened and team_key == load_settings().get("team_key"):
        _access = opened
    return opened


def set_team_key(team_key):
    """Remember the team key on this PC if it's right. Returns True when it is."""
    global _access
    opened = access(team_key)
    if not opened:
        return False
    remember("team_key", team_key.strip())
    _access = opened
    send_soon()
    return True


def pending():
    return len(list(QUEUE.glob("*.json"))) if QUEUE.exists() else 0


def queue(picture, rgb, version):
    """Keep a lesson for one counted picture, to be sent. picture: the screen's record of it."""
    from PIL import Image

    QUEUE.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H-%M-%S")
    name = f"{stamp} {Path(picture['path']).stem[:60]} {uuid.uuid4().hex[:6]}"
    img = Image.fromarray(rgb)
    scale = min(1.0, SIDE / max(img.size))
    if scale < 1:
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=85)
    s = lambda points: [[round(x * scale, 1), round(y * scale, 1)] for x, y in points or []]   # noqa: E731
    lesson = {
        "picture": name + ".jpg", "original_name": Path(picture["path"]).name, "date": stamp,
        "computer": os.environ.get("COMPUTERNAME", ""), "app_version": version,
        "width": img.width, "height": img.height, "scale": round(scale, 5),
        "mode": picture.get("mode"), "sensitivity": picture.get("sensitivity"),
        "example": s([picture["example"][:2], picture["example"][2:]]) if picture.get("example") else None,
        "diameter": round(picture["diameter"] * scale, 1) if picture.get("diameter") else None,
        "found": s(picture.get("found")),               # what the counter marked
        "final": s(picture.get("points")),              # after the person's corrections: the right answer
        "added": picture.get("added", 0), "removed": picture.get("removed", 0),
    }
    (QUEUE / (name + ".jpg")).write_bytes(buffer.getvalue())
    (QUEUE / (name + ".json")).write_text(json.dumps(lesson, indent=1), encoding="utf-8")


def send_soon():
    """Send the queued lessons in the background (if this PC has the team key and nothing is being sent)."""
    global _uploading
    with _lock:
        if _uploading or not pending() or access() is None:
            return
        _uploading = True
    threading.Thread(target=_send, daemon=True).start()


def _send():
    global _uploading
    try:
        from .gdrive import Drive
        opened = access()
        drive = Drive(opened["key"])
        month = drive.folder(drive.folder(opened["drive"], "lessons"), time.strftime("%Y-%m"))
        for lesson in sorted(QUEUE.glob("*.json")):
            picture = lesson.with_suffix(".jpg")
            if picture.exists():
                drive.upload(month, picture.name, picture.read_bytes(), "image/jpeg")
            drive.upload(month, lesson.name, lesson.read_bytes(), "application/json")
            lesson.unlink()                              # sent: the lesson file goes first, so a half-sent one
            picture.unlink(missing_ok=True)              # is sent again whole rather than lost
    except Exception:
        pass                                             # no internet, Google down...: tried again next time
    finally:
        with _lock:
            _uploading = False

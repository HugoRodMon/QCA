"""Self-update from GitHub Releases.

On start the app asks GitHub for the latest release. If its tag (v1.3.0) is newer than the running
version, the user is offered the update; the new .exe is downloaded next to the current one, the
running .exe is renamed to <name>.old.exe (Windows allows renaming a running program, not deleting
it), the new one takes its place and is started. The .old.exe is deleted on the next start.

The file keeps whatever name it has on the user's PC: apps that started as PriceExtractor.exe (before
the suite became DQS Apps) stay under that name, so their shortcuts keep working.

Only does anything when running as the built .exe (not when running dqs.py with Python).
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from version import EXE_NAME, UPDATE_REPO, __version__

# PRICE_EXTRACTOR_UPDATE_URL points the updater somewhere else (used to test updates locally)
API = os.environ.get("PRICE_EXTRACTOR_UPDATE_URL") or f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
TIMEOUT = 8


def is_frozen():
    return getattr(sys, "frozen", False)


def current_exe():
    return Path(sys.executable)


def _sibling(kind):
    """<this exe's name>.new.exe / .old.exe, next to the running exe."""
    exe = current_exe()
    return exe.with_name(f"{exe.stem}.{kind}.exe")


def parse_version(text):
    """'v1.10.2' -> (1, 10, 2)"""
    return tuple(int(n) for n in re.findall(r"\d+", str(text))[:3]) or (0,)


def _get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "DQSApps-updater", "Accept": accept})
    token = os.environ.get("PRICE_EXTRACTOR_GITHUB_TOKEN")          # only needed for a private repository
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def check():
    """Returns {'version', 'notes', 'url', 'size'} if a newer release exists, else None.
    Never raises: no internet / GitHub down just means 'no update'."""
    try:
        with _get(API) as r:
            rel = json.load(r)
    except Exception:
        return None
    tag = rel.get("tag_name", "")
    if parse_version(tag) <= parse_version(__version__):
        return None
    asset = next((a for a in rel.get("assets", []) if a.get("name", "").lower() == EXE_NAME.lower()), None)
    if not asset:
        return None
    return {"version": tag.lstrip("vV"), "notes": (rel.get("body") or "").strip(),
            "url": asset["browser_download_url"], "size": asset.get("size", 0)}


def download(info, progress=None):
    """Download the new .exe next to the running one. Returns its path."""
    target = _sibling("new")
    with _get(info["url"], accept="application/octet-stream") as r, open(target, "wb") as f:
        total, done = info.get("size") or int(r.headers.get("Content-Length", 0)), 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    with open(target, "rb") as f:
        if f.read(2) != b"MZ":                       # not a Windows program: don't install it
            target.unlink(missing_ok=True)
            raise RuntimeError("the downloaded file is not a valid program")
    if total and target.stat().st_size != total:
        target.unlink(missing_ok=True)
        raise RuntimeError("the download was incomplete")
    return target


def install_and_restart(new_exe):
    """Swap the .exe files and start the new version. The caller must close the app right after."""
    exe = current_exe()
    old = _sibling("old")
    old.unlink(missing_ok=True)
    exe.rename(old)                                  # allowed while running
    try:
        new_exe.rename(exe)
    except Exception:
        old.rename(exe)                              # put things back
        raise
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")   # new process unpacks its own files
    subprocess.Popen([str(exe)], env=env, close_fds=True)


def cleanup_old():
    """Delete the previous version left behind by the last update (and a failed download)."""
    if not is_frozen():
        return
    for kind in ("old", "new"):
        try:
            _sibling(kind).unlink(missing_ok=True)
        except OSError:
            pass                                     # still closing; next start will get it

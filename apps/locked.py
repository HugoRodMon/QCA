"""Private apps: published encrypted, opened with the secret key.

The repository and the .exe only contain locked/apps.enc. Its contents (even the apps' names) can't be
read or run without the key, because the key is what decrypts them: it isn't stored anywhere in the
code. To change the apps or the key: tools/lock_apps.py (their source stays in private_apps/ on your PC).
"""
import base64
import hashlib
import json
import os
import sys
import types
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

BUNDLE = Path(__file__).parent / "locked" / "apps.enc"
ITERATIONS = 600_000            # slows down anyone trying keys one after another


def _fernet(key, salt):
    derived = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, ITERATIONS)
    return Fernet(base64.urlsafe_b64encode(derived))


def lock(apps, key):
    """apps: [{id, title, description, source}] -> encrypted bytes."""
    salt = os.urandom(16)
    token = _fernet(key, salt).encrypt(json.dumps(apps).encode("utf-8"))
    return base64.urlsafe_b64encode(salt) + b"." + token


def unlock(key, path=BUNDLE):
    """The private apps, or None if the key is wrong (or there's no bundle)."""
    try:
        salt, token = path.read_bytes().split(b".", 1)
        apps = json.loads(_fernet(key, base64.urlsafe_b64decode(salt)).decrypt(token))
    except (OSError, ValueError, InvalidToken):
        return None
    return apps


def load_module(app):
    """Turn a decrypted app's source into a module. It must define open_app(master)."""
    name = f"dqs_private_{app['id']}"
    module = types.ModuleType(name)
    sys.modules[name] = module                     # dataclasses and friends look modules up here
    exec(compile(app["source"], name, "exec"), module.__dict__)
    return module

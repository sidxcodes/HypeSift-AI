"""Object storage behind a small interface.

Local disk is the default (free, zero setup). Keys look like
``projects/<id>/source.mp4``; an S3-compatible backend only needs to implement the
same five methods. Downloads use HMAC-signed, expiring links so a URL leaked from a
browser stops working after ``ttl`` seconds.
"""

from __future__ import annotations

import hashlib
import hmac
import shutil
import time
from pathlib import Path

from .config import get_settings


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root):  # path traversal guard
            raise ValueError("invalid storage key")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def exists(self, key: str | None) -> bool:
        return bool(key) and self.path(key).exists()

    def delete_prefix(self, prefix: str) -> None:
        p = self.path(prefix)
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink(missing_ok=True)

    def size(self, key: str) -> int:
        return self.path(key).stat().st_size


storage = LocalStorage(get_settings().storage_dir)


def sign(key: str, ttl: int = 3600, download_name: str | None = None) -> str:
    """Return a query string granting access to ``key`` until now+ttl."""
    exp = int(time.time()) + ttl
    msg = f"{key}|{exp}".encode()
    sig = hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).hexdigest()[:32]
    q = f"key={key}&exp={exp}&sig={sig}"
    if download_name:
        from urllib.parse import quote

        q += f"&dl={quote(download_name)}"
    return q


def verify(key: str, exp: int, sig: str) -> bool:
    if exp < time.time():
        return False
    msg = f"{key}|{exp}".encode()
    good = hmac.new(get_settings().secret_key.encode(), msg, hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(good, sig)

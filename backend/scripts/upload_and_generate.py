"""CLI: send a local video or a video link to a running HypeSift API and run AI Generate.

    python scripts/upload_and_generate.py VIDEO_OR_LINK --email you@example.com --password ... [--api URL]

VIDEO_OR_LINK is a file path, a YouTube / TikTok / Vimeo … link or a direct .mp4 link. Files use the same
resumable chunked-upload protocol as the web app. Prints real job progress.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="a video file, or a YouTube/TikTok/Vimeo/... or direct .mp4 link")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--preset", default="bold_creator")
    a = ap.parse_args()

    c = httpx.Client(base_url=a.api, timeout=120)
    r = c.post("/api/auth/login", json={"email": a.email, "password": a.password})
    if r.status_code == 401:
        r = c.post("/api/auth/signup", json={"email": a.email, "password": a.password, "name": "CLI"})
    r.raise_for_status()

    settings = {
        "count": a.count,
        "min_dur": 15,
        "max_dur": 45,
        "caption_preset": a.preset,
        "platforms": ["youtube", "instagram", "tiktok", "linkedin"],
    }
    if "://" in a.video or a.video.startswith(("www.", "youtu")):
        t = time.time()
        info = c.post("/api/url/check", json={"url": a.video})
        if info.status_code != 200:
            sys.exit(f"link refused: {info.json().get('detail')}")
        info = info.json()
        print(
            f"{info['platform']}: {info['title']!r} by {info['author']} ({info['duration']}s), checked in "
            f"{time.time() - t:.1f}s"
        )
        if not info["importable"]:
            sys.exit(f"not importable: {info['message']}")
        p = c.post("/api/projects", json={"url": info["url"], "settings": settings})
    else:
        p = c.post("/api/projects", json={"upload_id": _upload(c, Path(a.video)), "settings": settings})
    if p.status_code != 200:
        sys.exit(f"refused: {p.json().get('detail')}")
    _follow(c, p.json(), a.api)


def _upload(c: httpx.Client, path: Path) -> str:
    size = path.stat().st_size
    up = c.post("/api/uploads", json={"filename": path.name, "size": size}).json()
    with open(path, "rb") as f:
        offset = 0
        while offset < size:
            chunk = f.read(up["chunk_size"])
            offset = c.put(f"/api/uploads/{up['id']}?offset={offset}", content=chunk).json()["received"]
            print(f"\rupload {offset / size:6.1%}", end="", flush=True)
    print()
    c.post(f"/api/uploads/{up['id']}/complete").raise_for_status()
    return up["id"]


def _follow(c: httpx.Client, p: dict, api: str) -> None:
    print("project", p["id"], p["name"])
    t0, last = time.time(), ""
    while True:
        p = c.get(f"/api/projects/{p['id']}").json()
        j = p["job"]
        line = f"{j['status']:9s} {j['progress']:6.1%}  {j['message'][:70]}"
        if line != last:
            print(f"{time.time() - t0:6.1f}s  {line}", flush=True)
            last = line
        if j["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(1.5)
    if p["status"] != "ready":
        sys.exit(f"failed: {p['error']}")
    for clip in p["clips"]:
        print(f"{clip['score']:3d}  {clip['title']}  ({clip['output_duration']}s)  {api}{clip['download_url']}")
    print("analysis:", {k: p["analysis"].get(k) for k in ("genre", "stt_engine", "ranking_engine", "seconds")})


if __name__ == "__main__":
    main()

"""CLI: upload a local video to a running HypeSift API and run AI Generate.

    python scripts/upload_and_generate.py VIDEO --email you@example.com --password ... [--api http://127.0.0.1:8000]

Uses the same resumable chunked-upload protocol as the web app and prints real job progress.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--preset", default="bold_creator")
    a = ap.parse_args()

    path = Path(a.video)
    c = httpx.Client(base_url=a.api, timeout=120)
    r = c.post("/api/auth/login", json={"email": a.email, "password": a.password})
    if r.status_code == 401:
        r = c.post("/api/auth/signup", json={"email": a.email, "password": a.password, "name": "CLI"})
    r.raise_for_status()

    size = path.stat().st_size
    up = c.post("/api/uploads", json={"filename": path.name, "size": size}).json()
    with open(path, "rb") as f:
        offset = 0
        while offset < size:
            chunk = f.read(up["chunk_size"])
            offset = c.put(f"/api/uploads/{up['id']}?offset={offset}", content=chunk).json()["received"]
            print(f"\rupload {offset / size:6.1%}", end="", flush=True)
    print()
    done = c.post(f"/api/uploads/{up['id']}/complete")
    done.raise_for_status()

    settings = {
        "count": a.count,
        "min_dur": 15,
        "max_dur": 45,
        "caption_preset": a.preset,
        "platforms": ["youtube", "instagram", "tiktok", "linkedin"],
    }
    p = c.post("/api/projects", json={"upload_id": up["id"], "name": path.stem, "settings": settings}).json()
    print("project", p["id"])
    while True:
        p = c.get(f"/api/projects/{p['id']}").json()
        j = p["job"]
        print(f"\r{j['status']:9s} {j['progress']:6.1%} {j['message'][:60]:60s}", end="", flush=True)
        if j["status"] in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(1.5)
    print()
    if p["status"] != "ready":
        sys.exit(f"failed: {p['error']}")
    for clip in p["clips"]:
        print(f"{clip['score']:3d}  {clip['title']}  ({clip['output_duration']}s)  {a.api}{clip['download_url']}")
    print("analysis:", {k: p["analysis"].get(k) for k in ("genre", "stt_engine", "ranking_engine", "seconds")})


if __name__ == "__main__":
    main()

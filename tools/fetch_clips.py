"""Fetch the CC BY clips for the sports in scope into data/local/clips/ (gitignored).

    python tools/fetch_clips.py              # every clip below
    python tools/fetch_clips.py --sport basketball --dry-run

Before downloading, it checks each video's license on YouTube (yt-dlp's `license` field) and skips anything that
isn't Creative Commons Attribution. It downloads only the listed segments (or whole short videos) at <= 720p by default, retried and length-checked because flaky Wi-Fi leaves short files, and writes credits to
data/clips/credits.json (CC BY requires attribution in anything we share). Needs `yt-dlp` and `ffmpeg` on PATH,
or `--yt-dlp <path>`. Source list and rationale: docs/plan/clip-library.md. People appear in these clips, so blur
anyone who hasn't consented before publishing anything derived from them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "local" / "clips"
CREDITS = ROOT / "data" / "clips" / "credits.json"
SRC = OUT / "_src"

# (sport, youtube id, sections as "start-end" or None for the whole video, what it's for)
CLIPS: list[tuple[str, str, list[str] | None, str]] = [
    ("table_tennis", "7maQFqJ3XQ0", None, "club match; disputed edge ball at 8:36; backup demo"),
    ("basketball", "2NxcgKW7xFM", ["0:00-12:00"], "half court facing one hoop; score overlay = make/miss and 2/3 truth"),
    ("pickleball", "QhLECLlXU3c", None, "both kitchens + feet visible; near-line balls; score overlay"),
    ("tennis", "JReOUveKesY", ["0:00-10:00"], "3.5 doubles, behind the baseline corner; close line calls"),
    ("badminton", "ShrdcaZMdS0", ["0:00-8:00", "41:30-43:30"], "wide static corner; landing in/out; a let at 42:22"),
    ("volleyball", "kVpO4ypzPYU", None, "full amateur set, static elevated; in/out, net"),
    ("two_hand_touch", "V6nJyuKNstQ", None, "flag-football rule clip: illegal snap (pre-labelled)"),
    ("two_hand_touch", "Q4Bc-_4Menk", None, "flag guarding"),
    ("two_hand_touch", "ia4vDkeKfG8", None, "illegal flag pull"),
    ("two_hand_touch", "0oy3ZeCtAvo", None, "false start"),
    ("two_hand_touch", "U5-Zpli85MY", None, "defensive pass interference"),
    ("two_hand_touch", "1KHE6Te6JLA", None, "illegal forward pass"),
    ("two_hand_touch", "KoEpbHSChIg", None, "illegal motion"),
    ("two_hand_touch", "cdzbER-7PHI", None, "blocking"),
    # Not fetched: LLNlE3QnCcs ("12u 7v7 ... Scrimmage") shows minors. A CC BY license covers copyright, not the
    # participants' permission (CLAUDE.md safeguard 4). Film our own two-hand touch instead.
]


RETRY = ["--retries", "infinite", "--fragment-retries", "infinite", "--retry-sleep", "exp=2:60",
         "--socket-timeout", "30", "--continue", "--no-part"]


def yt(ytdlp: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([ytdlp, *args], capture_output=True, text=True, encoding="utf-8")


def info(ytdlp: str, vid: str, attempts: int = 6) -> dict:
    """Video metadata, retried with backoff: flaky Wi-Fi drops DNS lookups for a minute at a time."""
    err = ""
    for i in range(attempts):
        r = yt(ytdlp, "-J", "--no-warnings", "--socket-timeout", "30", f"https://www.youtube.com/watch?v={vid}")
        if r.returncode == 0:
            return json.loads(r.stdout)
        err = r.stderr.strip()[-300:]
        time.sleep(min(60, 5 * 2**i))
    raise RuntimeError(err)


def seconds(t: str) -> float:
    out = 0.0
    for part in t.split(":"):
        out = out * 60 + float(part)
    return out


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def fmt(h: int) -> str:
    return f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/b[height<={h}][ext=mp4]/b[height<={h}]"


def download_source(ytdlp: str, vid: str, want_s: float, height: int, attempts: int = 4) -> Path | None:
    """The whole video at <= 1080p, resumable (segment downloads stream through ffmpeg and can't resume), with
    the result checked against YouTube's duration."""
    SRC.mkdir(parents=True, exist_ok=True)
    out = SRC / f"{vid}.mp4"
    if out.exists() and abs(duration(out) - want_s) <= 2:
        return out
    for _ in range(attempts):
        r = yt(ytdlp, "-f", fmt(height),
               "--merge-output-format", "mp4", "--no-playlist", "--no-warnings", *RETRY,
               "-o", str(SRC / f"{vid}.%(ext)s"), f"https://www.youtube.com/watch?v={vid}")
        if r.returncode == 0 and out.exists() and abs(duration(out) - want_s) <= 2:
            return out
        print(f"  retrying {vid}: {(r.stderr.strip() or 'short file')[-200:]}")
        time.sleep(15)
    return None


def download_section(ytdlp: str, vid: str, dest: Path, section: str, height: int, attempts: int = 5) -> bool:
    """Only the needed span (a 12-minute section of a 32-minute game), retried until its length checks out:
    section downloads stream through ffmpeg, so a dropped connection leaves a short file rather than an error."""
    a, b = (seconds(x) for x in section.split("-"))
    for _ in range(attempts):
        dest.unlink(missing_ok=True)
        yt(ytdlp, "-f", fmt(height), "--merge-output-format", "mp4", "--no-playlist", "--no-warnings", *RETRY,
           "--download-sections", f"*{section}", "-o", str(dest), f"https://www.youtube.com/watch?v={vid}")
        if dest.exists() and abs(duration(dest) - (b - a)) <= 2:
            return True
        print(f"  retrying {vid} {section}: got {duration(dest) if dest.exists() else 0:.1f}s of {b - a:.0f}s", flush=True)
        time.sleep(15)
    dest.unlink(missing_ok=True)
    return False


def cut(src: Path, dest: Path, section: str) -> bool:
    a, b = (seconds(x) for x in section.split("-"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", str(src), "-c", "copy",
                    "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(dest)], check=False)
    ok = dest.exists() and abs(duration(dest) - (b - a)) <= 2
    if not ok:
        dest.unlink(missing_ok=True)
    return ok


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # titles carry emoji; Windows consoles default to cp1252
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-source", action="store_true", help="keep full downloads in data/local/clips/_src")
    ap.add_argument("--max-height", type=int, default=720, help="720 matches the live pipeline; 1080 for replays")
    ap.add_argument("--yt-dlp", default=shutil.which("yt-dlp") or "yt-dlp")
    a = ap.parse_args()

    credits = json.loads(CREDITS.read_text("utf8")) if CREDITS.exists() else []
    by_url = {c.get("url"): c for c in credits}
    failed = 0
    for sport, vid, sections, why in CLIPS:
        if a.sport and sport != a.sport:
            continue
        url = f"https://www.youtube.com/watch?v={vid}"
        try:
            meta = info(a.yt_dlp, vid)
        except RuntimeError as e:
            print(f"SKIP {sport} {vid}: metadata failed: {e}")
            failed += 1
            continue
        lic = meta.get("license") or ""
        if "Creative Commons" not in lic or "Attribution" not in lic:
            print(f"SKIP {sport} {vid}: license is {lic!r}, not CC BY")
            failed += 1
            continue
        dest = OUT / sport
        dest.mkdir(parents=True, exist_ok=True)
        targets = [(dest / f"{vid}_{s.replace(':', '')}.mp4", s) for s in sections] if sections else [(dest / f"{vid}.mp4", None)]
        done = [t for t, s in targets if t.exists() and (s is None or abs(duration(t) - (seconds(s.split("-")[1]) - seconds(s.split("-")[0]))) <= 2)]
        print(f"{'PLAN' if a.dry_run else 'GET '} {sport} {vid} {sections or 'full'}  [{lic}] {meta.get('title')!r}", flush=True)
        if not a.dry_run and len(done) < len(targets):
            ok = True
            if sections:
                for t, s in targets:
                    if t not in done and not download_section(a.yt_dlp, vid, t, s, a.max_height):
                        print(f"FAIL {sport} {vid}: section {s} incomplete after retries", flush=True)
                        ok = False
            else:
                src = download_source(a.yt_dlp, vid, float(meta.get("duration") or 0), a.max_height)
                if src is None:
                    ok = False
                    print(f"FAIL {sport} {vid}: download incomplete after retries", flush=True)
                else:
                    shutil.copyfile(src, targets[0][0])
                    if not a.keep_source:
                        src.unlink(missing_ok=True)
            if not ok:
                failed += 1
                continue
        by_url[url] = {
            "sport": sport,
            "url": url,
            "title": meta.get("title"),
            "creator": meta.get("uploader") or meta.get("channel"),
            "license": lic,
            "sections": sections or ["full"],
            "use": why,
            "credit_line": f"\"{meta.get('title')}\" by {meta.get('uploader') or meta.get('channel')}, {lic}, {url}",
        }
    if not a.dry_run:
        CREDITS.write_text(json.dumps(sorted(by_url.values(), key=lambda c: (c["sport"], c["url"])), indent=2) + "\n", "utf8")
    print(f"done; {failed} skipped or failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

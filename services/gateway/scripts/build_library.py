"""Build the preloaded multi-camera games the dashboard plays without an upload (data/local/clips/library/<id>/).

    uv run python scripts/build_library.py tt3d --game game_00          # TT3D raw dataset: side + oblique views
    uv run python scripts/build_library.py edmonton2015                 # 2015 Edmonton Open final: side + overhead
    uv run python scripts/build_library.py check                        # list what the gateway will see

Each preset is a folder with one video per camera and a preset.json the gateway's /api/demo/library reads:
{preset_id, title, sport, source, license, notes, mode, cameras: [{label, video, corners_norm[4][2], offset_s,
duration_s}]}. Corners are in Trophy's order (A-near, B-near, B-far, A-far, i.e. CORNERS_M in stream_clips.py), as a
fraction of the 1280x720 frame the streamer sends, so the same table end is "A" in every camera. Every camera also gets
an `overlay_<label>.jpg` (first frame + the corners) to eyeball.

tt3d: the per-rally clips of one recording are concatenated per view into one continuous video (hard cuts between
rallies; the two views are cut from the same moments, so they stay aligned to the frame). Corners are projected from
the dataset's own camera pose (rvec, tvec, f; principal point assumed at the image centre).
edmonton2015: the two YouTube downloads start at different moments, so the overhead camera's offset is measured by
cross-correlating the two soundtracks; corners come from the tabletop detector (spikes/serve-analysis) or
--corners LABEL=x1,y1,...,x4,y4 (0..1).

Footage stays in data/local (gitignored). Licenses: see each preset's `license`; nothing here is redistributed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
LIBRARY = ROOT / "data" / "local" / "clips" / "library"
SERVE_ANALYSIS = ROOT / "spikes" / "serve-analysis"
W, H = 1280, 720
VF = f"fps=30,scale={W}:{H}:force_original_aspect_ratio=decrease:flags=area,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"
LENGTH_M, WIDTH_M = 2.74, 1.525
# Trophy's corner order (stream_clips.CORNERS_M): A end is X < 0 along the table's long axis
CORNERS_M = [
    (-LENGTH_M / 2, -WIDTH_M / 2),
    (LENGTH_M / 2, -WIDTH_M / 2),
    (LENGTH_M / 2, WIDTH_M / 2),
    (-LENGTH_M / 2, WIDTH_M / 2),
]


def ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def sh(*cmd: str, timeout: float = 3600) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise SystemExit(f"{cmd[0]} failed: {r.stderr.strip()[-800:]}")
    return r.stdout


def probe(path: Path) -> dict:
    out = sh(
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height,avg_frame_rate:format=duration", "-of", "json", str(path),
    )  # fmt: skip
    d = json.loads(out)
    v = d["streams"][0]
    num, _, den = v["avg_frame_rate"].partition("/")
    return {
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": round(float(num) / float(den or 1), 3),
        "duration_s": round(float(d["format"]["duration"]), 3),
    }


def encode(args: list[str], out: Path) -> None:
    """H.264 1080p-ish with VideoToolbox, software x264 if that fails."""
    base = [ffmpeg(), "-v", "error", "-y", *args, "-an", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    r = subprocess.run([*base, "-c:v", "h264_videotoolbox", "-b:v", "10M", str(out)], capture_output=True, text=True)
    if r.returncode:
        sh(*base, "-c:v", "libx264", "-crf", "18", "-preset", "fast", str(out))


def first_frame(video: Path) -> Image.Image:
    raw = subprocess.run(
        [ffmpeg(), "-v", "error", "-i", str(video), "-frames:v", "1", "-vf", VF, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],  # noqa: E501
        capture_output=True,
    ).stdout  # fmt: skip
    return Image.frombytes("RGB", (W, H), raw[: W * H * 3])


def overlay(video: Path, corners: list[list[float]], out: Path) -> None:
    im = first_frame(video)
    dr = ImageDraw.Draw(im)
    pts = [(x * W, y * H) for x, y in corners]
    dr.polygon(pts, outline=(255, 60, 60), width=3)
    for (x, y), name in zip(pts, ("A·near", "B·near", "B·far", "A·far"), strict=True):
        dr.ellipse([x - 6, y - 6, x + 6, y + 6], fill=(255, 220, 0))
        dr.text((x + 8, y - 14), name, fill=(255, 255, 255))
    im.save(out, quality=85)


def write_preset(d: Path, meta: dict) -> None:
    for cam in meta["cameras"]:
        overlay(d / cam["video"], cam["corners_norm"], d / f"overlay_{cam['label']}.jpg")
        cam.update({k: v for k, v in probe(d / cam["video"]).items() if k in ("duration_s", "fps", "width", "height")})
        (d / f"frame0_{cam['label']}.jpg").unlink(missing_ok=True)  # the gateway rebuilds it on demand
    (d / "preset.json").write_text(json.dumps(meta, indent=2), encoding="utf8")
    print(json.dumps({k: v for k, v in meta.items() if k != "cameras"}, indent=2))
    for cam in meta["cameras"]:
        print(f"  {cam['label']}: {cam['video']} {cam.get('width')}x{cam.get('height')}@{cam.get('fps')} "
              f"{cam.get('duration_s')} s offset {cam.get('offset_s', 0)} s -> overlay_{cam['label']}.jpg")  # fmt: skip


# --- TT3D -------------------------------------------------------------------------------------------------------------


def rodrigues(rvec: np.ndarray) -> np.ndarray:
    th = float(np.linalg.norm(rvec))
    if th < 1e-12:
        return np.eye(3)
    k = rvec / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * K + (1 - np.cos(th)) * (K @ K)


def tt3d_corners(pose_yaml: Path, size: tuple[int, int]) -> list[list[float]]:
    """Project the table corners with the dataset's pose. TT3D's table frame: X = short side, Y = long side, Z up,
    origin at the table centre; Trophy's X is the long side, so (X_trophy, Y_trophy) -> (y, x) here."""
    vals = {}
    for line in pose_yaml.read_text("utf8").splitlines():
        k, _, v = line.partition(":")
        vals[k.strip()] = json.loads(v.strip()) if v.strip().startswith("[") else float(v)
    R, t, f = rodrigues(np.array(vals["rvec"], float)), np.array(vals["tvec"], float), float(vals["f"])
    cx, cy = size[0] / 2, size[1] / 2
    out = []
    for X, Y in CORNERS_M:
        p = R @ np.array([Y, X, 0.0]) + t
        u, v = f * p[0] / p[2] + cx, f * p[1] / p[2] + cy
        out.append([round(u / size[0], 6), round(v / size[1], 6)])  # 16:9 source -> no padding in the 1280x720 frame
    return out


def build_tt3d(game: str) -> None:
    src = LIBRARY / "tt3d" / "src"
    d = LIBRARY / f"tt3d_{game}"
    d.mkdir(parents=True, exist_ok=True)
    cams = []
    for view in ("side", "oblique"):
        clips = sorted((src / view / game).glob("*.mp4"))
        if not clips:
            raise SystemExit(f"no clips in {src / view / game}; download the TT3D raw dataset first")
        lst = d / f"concat_{view}.txt"
        lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf8")
        out = d / f"{view}.mp4"
        if not out.exists():
            print(f"concatenating {len(clips)} {view} rallies -> {out.name}")
            encode(["-f", "concat", "-safe", "0", "-i", str(lst)], out)
        info = probe(out)
        corners = tt3d_corners(src / view / f"{game}_table_pose.yaml", (info["width"], info["height"]))
        cams.append({"label": view, "video": out.name, "corners_norm": corners, "offset_s": 0.0})
    write_preset(
        d,
        {
            "preset_id": d.name,
            "title": f"TT3D {game.replace('_', ' ')} (Tübingen): side + oblique",
            "sport": "table_tennis",
            "source": "TT3D raw dataset, Gossard & Ziegler, Uni Tübingen "
            "(cloud.cs.uni-tuebingen.de/index.php/s/SCKq85JZEmKoC6J)",
            "license": "dataset license unstated (code MIT): local evaluation only, do not publish",
            "notes": f"{len(list((src / 'side' / game).glob('*.mp4')))} rallies cut back to back from the same two "
            "fixed cameras (hard cuts between rallies). Corners projected from the dataset's camera poses. "
            "200 Hz 3D ball ground truth sits in src/3d_tracking for accuracy checks.",
            "mode": "simultaneous",
            "cameras": cams,
        },
    )


# --- Edmonton 2015 ----------------------------------------------------------------------------------------------------


def envelope(video: Path, rate: int = 8000, hop: int = 80) -> np.ndarray:
    raw = subprocess.run(
        [ffmpeg(), "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        capture_output=True,
    ).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32)
    n = len(x) // hop
    env = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1))
    env = np.log1p(env)
    return env - env.mean()


def audio_offset_s(ref: Path, other: Path, max_s: float = 300.0) -> tuple[float, float]:
    """Seconds `other` starts after `ref` (negative: before), by cross-correlating 100 Hz loudness envelopes."""
    a, b = envelope(ref), envelope(other)
    hz = 100
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    cc = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    lags = np.arange(n)
    lags[lags > n // 2] -= n
    keep = np.abs(lags) <= max_s * hz
    i = np.argmax(cc[keep])
    lag = lags[keep][i]  # a[t] ~ b[t - lag]  =>  b starts `lag` samples after a
    peak = cc[keep][i] / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
    return round(lag / hz, 2), round(float(peak), 3)


def detected_corners(video: Path) -> list[list[float]] | None:
    py = SERVE_ANALYSIS / ".venv" / "bin" / "python"
    if not py.exists():
        return None
    r = subprocess.run(
        [str(py), "scripts/suggest_table_corners.py", str(video), "--width", str(W)],
        cwd=SERVE_ANALYSIS, capture_output=True, text=True, timeout=120,
    )  # fmt: skip
    if r.returncode:
        return None
    try:
        d = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return d.get("corners_norm")


def build_edmonton(manual: dict[str, list[list[float]]]) -> None:
    d = LIBRARY / "edmonton2015"
    src = d / "src"
    files = {"side": src / "D-FHYCRTdEc.mp4", "overhead": src / "YSzOgrITjJI.mp4"}
    for p in files.values():
        if not p.exists():
            raise SystemExit(
                f"{p} missing: download it first (see docs/research/clips-table-tennis-multiview-2026-10-24.md)"
            )
    cams = []
    offset, peak = audio_offset_s(files["side"], files["overhead"])
    print(f"overhead starts {offset} s after side (envelope correlation peak {peak})")
    for label, p in files.items():
        out = d / f"{label}.mp4"
        if not out.exists():
            print(f"re-encoding {p.name} -> {out.name} (1080p max, no audio)")
            encode(["-i", str(p), "-vf", "scale='min(1920,iw)':-2"], out)
        corners = manual.get(label) or detected_corners(out)
        if not corners:
            raise SystemExit(f"{label}: no table corners detected; pass --corners {label}=x1,y1,...,x4,y4 (0..1)")
        cams.append(
            {
                "label": label,
                "video": out.name,
                "corners_norm": corners,
                "offset_s": offset if label == "overhead" else 0.0,
            }
        )
    write_preset(
        d,
        {
            "preset_id": d.name,
            "title": "2015 Edmonton Open final: side + overhead",
            "sport": "table_tennis",
            "source": "YouTube D-FHYCRTdEc (side) + YSzOgrITjJI (overhead), Edmonton Table Tennis Club uploader",
            "license": "standard YouTube license: local demo only; ask the uploader before any publication",
            "notes": f"Kenny Li vs Ioulia Degtiar, 2015-09-06. Angles aligned by soundtrack correlation (overhead "
            f"+{offset} s, peak {peak}). Corners from the tabletop detector or tapped: untrusted, calls cap at BETA.",
            "mode": "simultaneous",
            "cameras": cams,
        },
    )


def check() -> None:
    sys.path.insert(0, str(ROOT / "services" / "gateway"))
    from gateway.demo import load_presets

    for p in load_presets(LIBRARY):
        print(p["preset_id"], "ERROR " + p["error"] if p.get("error") else f"{len(p['cameras'])} cameras OK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tt3d")
    t.add_argument("--game", default="game_00", choices=["warmup", "game_00", "game_01"])
    e = sub.add_parser("edmonton2015")
    e.add_argument("--corners", action="append", default=[], help="LABEL=x1,y1,...,x4,y4 (0..1), overrides detection")
    sub.add_parser("check")
    a = ap.parse_args()
    if a.cmd == "tt3d":
        build_tt3d(a.game)
    elif a.cmd == "edmonton2015":
        manual = {}
        for kv in a.corners:
            label, _, nums = kv.partition("=")
            v = [float(x) for x in re.split(r"[ ,]+", nums.strip())]
            if len(v) != 8:
                raise SystemExit(f"--corners {label}: need 8 numbers")
            manual[label] = [[v[i], v[i + 1]] for i in range(0, 8, 2)]
        build_edmonton(manual)
    else:
        check()
    return 0


if __name__ == "__main__":
    sys.exit(main())

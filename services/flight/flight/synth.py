"""Synthetic two-camera table-tennis rally with ground truth: videos, true 3D track, bounces, hits, serve.

Labelled SYNTHETIC. It exists so every stage can be measured before real footage arrives; numbers from it are not
accuracy claims about real video. Physics: gravity, a restitution bounce, simple racket hits, no spin, no drag.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from .calib import Camera, camera_looking_at
from .field import BALL_RADIUS_M, CORNERS_M, LENGTH_M, NET_HEIGHT_M, NET_OVERHANG_M, TABLE_HEIGHT_M, WIDTH_M, on_table

G = 9.81
DEFAULT_CAMERAS = {
    "side": dict(pos=(0.0, -3.2, 1.9), look_at=(0.0, 0.0, 0.3), f_px=1000.0),
    "diag": dict(pos=(3.0, 2.6, 2.1), look_at=(0.0, 0.0, 0.2), f_px=1050.0),
}


def _aimed_velocity(rng, pos, target, net_clear_m=0.20, tries=25):
    """Velocity that reaches `target` on a parabola and clears the net at x = 0 by net_clear_m; None if impossible."""
    for _ in range(tries):
        flight_s = rng.uniform(0.3, 0.65)
        vel = (target - pos) / flight_s + np.array([0, 0, 0.5 * G * flight_s])
        if np.sign(pos[0]) == np.sign(target[0]):
            return vel
        s = -pos[0] / (target[0] - pos[0]) * flight_s
        z_net = pos[2] + vel[2] * s - 0.5 * G * s * s
        if z_net > NET_HEIGHT_M + net_clear_m:
            return vel
    return None


def _serve_velocity(rng, pos, tries=40):
    """Serve: first bounce on the server's half, rebound clears the net and lands on the far half. Returns (vel, e)."""
    for _ in range(tries):
        e = rng.uniform(0.80, 0.90)
        flight_s = rng.uniform(0.25, 0.4)
        target = np.array([rng.uniform(-0.9, -0.3), rng.uniform(-0.3, 0.3), BALL_RADIUS_M])
        vel = (target - pos) / flight_s + np.array([0, 0, 0.5 * G * flight_s])
        vz_in = vel[2] - G * flight_s
        v2 = np.array([vel[0] * 0.92, vel[1], -vz_in * e])
        s_net = -target[0] / v2[0]
        z_net = BALL_RADIUS_M + v2[2] * s_net - 0.5 * G * s_net**2
        t_land = (v2[2] + np.sqrt(v2[2] ** 2)) / G  # back to z = r
        x_land = target[0] + v2[0] * t_land
        if z_net > NET_HEIGHT_M + 0.08 and 0.3 < x_land < 1.2:
            return vel, e
    return None, None


def simulate(seed: int = 0, shots: int = 6, dt: float = 1 / 600.0) -> dict:
    """Serve toss + rally of `shots` hits, ending with a ball that goes long to the floor."""
    rng = np.random.default_rng(seed)
    t = 0.0
    rest_s = 0.5
    release = np.array([-LENGTH_M / 2 - 0.25, rng.uniform(-0.3, 0.3), 0.22])
    toss_h = rng.uniform(0.17, 0.30)
    vz0 = np.sqrt(2 * G * toss_h)
    tilt = np.deg2rad(rng.uniform(2, 12))  # the toss leans a little toward the table
    vel = np.array([vz0 * np.tan(tilt), 0.0, vz0])
    pos = release.copy()
    track, bounces, hits = [], [], []
    serve = {"release": {"t_s": rest_s, "xyz_m": release.tolist()}, "apex": None, "contact": None}
    phase = "rest"
    shot = 0
    dead = None
    apex_z = -1
    serve_e = None
    while t < 12.0:
        if phase == "rest":
            if t >= rest_s:
                phase = "toss"
        elif phase == "toss":
            vel[2] -= G * dt
            pos += vel * dt
            if pos[2] > apex_z:
                apex_z = pos[2]
                serve["apex"] = {"t_s": t, "xyz_m": pos.tolist()}
            if vel[2] < 0 and pos[2] <= release[2] + 0.02:
                # racket contact: a legal serve bounces on the server's half first, then crosses the net
                vel, serve_e = _serve_velocity(rng, pos)
                if vel is None:
                    break
                serve["contact"] = {"t_s": t, "xyz_m": pos.tolist()}
                hits.append({"t_s": t, "xyz_m": pos.tolist(), "side": "A"})
                phase = "rally"
        elif phase == "rally":
            vel[2] -= G * dt
            new = pos + vel * dt
            if new[2] <= BALL_RADIUS_M and pos[2] > BALL_RADIUS_M and vel[2] < 0 and on_table(new[0], new[1]):
                frac = (pos[2] - BALL_RADIUS_M) / max(1e-9, pos[2] - new[2])
                hit_pt = pos + vel * dt * frac
                hit_pt[2] = BALL_RADIUS_M
                bounces.append({"t_s": t + dt * frac, "xyz_m": hit_pt.tolist(), "side": "A" if hit_pt[0] < 0 else "B"})
                vel[2] = -vel[2] * (serve_e if len(bounces) == 1 and serve_e else rng.uniform(0.80, 0.90))
                vel[0] *= 0.92
                new = hit_pt + vel * dt * (1 - frac)
            if np.sign(new[0]) != np.sign(pos[0]) and new[2] < NET_HEIGHT_M + BALL_RADIUS_M:
                dead = {"t_s": t, "xyz_m": new.tolist(), "reason": "net"}
                pos = new
                track.append({"t_s": t, "xyz_m": pos.tolist()})
                break
            if new[2] <= -TABLE_HEIGHT_M + BALL_RADIUS_M:
                dead = {"t_s": t, "xyz_m": new.tolist(), "reason": "floor"}
                pos = new
                track.append({"t_s": t, "xyz_m": pos.tolist()})
                break
            pos = new
            # A return happens only after the ball bounced on the returner's side and has passed the end line.
            # The returner aims at a point on the far half (or long, for the final shot), so the flight is solvable.
            end_x = LENGTH_M / 2 + 0.15
            past_end = abs(pos[0]) > end_x and np.sign(pos[0]) == np.sign(vel[0])
            bounced_here = (
                bool(bounces)
                and bounces[-1]["t_s"] > hits[-1]["t_s"]
                and np.sign(bounces[-1]["xyz_m"][0]) == np.sign(pos[0])
            )
            if past_end and bounced_here and pos[2] > -0.25:
                direction = -np.sign(pos[0])
                side = "A" if pos[0] < 0 else "B"
                if shot < shots - 1:
                    target = np.array([direction * rng.uniform(0.35, 1.25), rng.uniform(-0.55, 0.55), BALL_RADIUS_M])
                else:
                    target = np.array([direction * (LENGTH_M / 2 + rng.uniform(0.4, 0.9)), rng.uniform(-0.4, 0.4), 0.0])
                aimed = _aimed_velocity(rng, pos, target)
                if aimed is None:
                    break  # no playable return from here: the rally is over
                vel = aimed
                hits.append({"t_s": t, "xyz_m": pos.tolist(), "side": side})
                shot += 1
        track.append({"t_s": t, "xyz_m": pos.tolist()})
        t += dt
    return {"dt_s": dt, "track": track, "bounces": bounces, "hits": hits, "serve": serve, "dead": dead}


def truth_at(sim: dict, t_s: float) -> np.ndarray | None:
    tr = sim["track"]
    i = int(round(t_s / sim["dt_s"]))
    if 0 <= i < len(tr) and abs(tr[i]["t_s"] - t_s) <= sim["dt_s"]:
        return np.array(tr[i]["xyz_m"])
    return None


def render(
    sim: dict,
    cam: Camera,
    out_path: Path,
    fps: float = 30.0,
    skew_s: float = 0.0,
    shutter_s: float = 1 / 120.0,
    distractors: bool = True,
    seed: int = 0,
) -> dict:
    """Write the camera's video. Frame k is exposed at t = k/fps + skew_s. Returns per-frame truth."""
    rng = np.random.default_rng(seed)
    w, h = cam.width, cam.height
    vw = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not vw.isOpened():
        raise RuntimeError("cv2.VideoWriter could not open " + str(out_path))
    bg = np.full((h, w, 3), (70, 72, 75), np.uint8)
    # floor and far wall gradient, so the background isn't flat
    for y in range(h):
        bg[y] = (60 + y * 30 // h, 62 + y * 25 // h, 66 + y * 20 // h)
    # table top, legs implied
    top = np.round(cam.project(CORNERS_M)).astype(np.int32)
    cv2.fillPoly(bg, [top], (120, 70, 25))
    cv2.polylines(bg, [top], True, (240, 240, 240), 2)
    centre = cam.project(np.array([[-LENGTH_M / 2, 0, 0], [LENGTH_M / 2, 0, 0]]))
    cv2.line(bg, tuple(np.round(centre[0]).astype(int)), tuple(np.round(centre[1]).astype(int)), (240, 240, 240), 1)
    net = cam.project(
        np.array(
            [
                [0, -WIDTH_M / 2 - NET_OVERHANG_M, 0],
                [0, WIDTH_M / 2 + NET_OVERHANG_M, 0],
                [0, WIDTH_M / 2 + NET_OVERHANG_M, NET_HEIGHT_M],
                [0, -WIDTH_M / 2 - NET_OVERHANG_M, NET_HEIGHT_M],
            ]
        )
    )
    overlay = bg.copy()
    cv2.fillPoly(overlay, [np.round(net).astype(np.int32)], (200, 200, 200))
    bg = cv2.addWeighted(overlay, 0.35, bg, 0.65, 0)
    cv2.polylines(bg, [np.round(net).astype(np.int32)], True, (235, 235, 235), 1)
    t_end = sim["track"][-1]["t_s"]
    frames = []
    k = 0
    while True:
        t = k / fps + skew_s
        if t > t_end:
            break
        img = bg.copy()
        if distractors:
            # two skin-coloured "hands" moving at each end, and a dark paddle: wrong blobs for the detector
            for sx, ph in ((-1, 0.0), (1, 1.3)):
                p = np.array(
                    [sx * (LENGTH_M / 2 + 0.45), 0.35 * np.sin(1.7 * t + ph), 0.35 + 0.1 * np.cos(2.3 * t + ph)]
                )
                c = cam.project(p)[0]
                r = int(cam.K[0, 0] * 0.05 / max(0.5, (cam.R @ p + cam.t)[2]))
                cv2.circle(img, tuple(np.round(c).astype(int)), r, (150, 170, 225), -1)
                c2 = cam.project(p + np.array([0, 0.12, 0.08]))[0]
                cv2.circle(img, tuple(np.round(c2).astype(int)), int(r * 1.3), (40, 40, 160), -1)
        # ball: positions across the exposure, drawn as a streak the ball's width
        pts = []
        for s in np.linspace(-shutter_s / 2, shutter_s / 2, 5):
            p = truth_at(sim, t + s)
            if p is not None:
                pts.append(p)
        if pts and t >= sim["serve"]["release"]["t_s"] - 0.3:
            pts = np.array(pts)
            depth = float(np.mean((cam.R @ pts.T).T[:, 2] + cam.t[2]))
            r_px = max(1.5, cam.K[0, 0] * BALL_RADIUS_M / depth)
            px = cam.project(pts)
            for a, b in zip(px[:-1], px[1:], strict=True):
                cv2.line(
                    img,
                    tuple(np.round(a).astype(int)),
                    tuple(np.round(b).astype(int)),
                    (250, 250, 250),
                    int(round(2 * r_px)),
                )
            cv2.circle(img, tuple(np.round(px[0]).astype(int)), int(round(r_px)), (250, 250, 250), -1)
            cv2.circle(img, tuple(np.round(px[-1]).astype(int)), int(round(r_px)), (250, 250, 250), -1)
            xyz = truth_at(sim, t)
            frames.append(
                {"frame": k, "t_s": t, "xyz_m": xyz.tolist(), "xy_px": cam.project(xyz)[0].tolist(), "r_px": r_px}
            )
        else:
            frames.append({"frame": k, "t_s": t, "xyz_m": None, "xy_px": None, "r_px": None})
        noise = rng.normal(0, 2.0, img.shape)
        img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        img = cv2.GaussianBlur(img, (3, 3), 0)
        vw.write(img)
        k += 1
    vw.release()
    return {"fps": fps, "skew_s": skew_s, "frames": frames, "corners_px": cam.project(CORNERS_M).tolist()}


def blurball_like_json(per_frame: dict, path: Path, noise_px: float, miss_p: float, false_p: float, seed: int = 0):
    """A tracker-branch-style cache from truth, with noise, misses and false blobs, for pipeline tests without video."""
    rng = np.random.default_rng(seed)
    rows = []
    for f in per_frame["frames"]:
        row = {"seq": f["frame"], "t_source_s": f["t_s"], "x": None, "y": None, "score": None, "status": "missing"}
        if f["xy_px"] is not None and rng.random() >= miss_p:
            x, y = np.array(f["xy_px"]) + rng.normal(0, noise_px, 2)
            row.update(x=float(x), y=float(y), score=float(rng.uniform(0.7, 1.0)), status="observed_2d")
        if rng.random() < false_p:
            row.update(x=float(rng.uniform(0, 1280)), y=float(rng.uniform(0, 720)), score=1.0, status="observed_2d")
        rows.append(row)
    Path(path).write_text(
        json.dumps({"frames": rows, "report": {"detector": "synthetic BlurBall-like", "synthetic": True}}),
        encoding="utf8",
    )


def make_dataset(out_dir: Path, seed: int = 0, fps: float = 30.0, skews: dict | None = None, shots: int = 6) -> dict:
    """Two videos + truth.json in out_dir. Camera skews default to 0 for `side` and +12 ms for `diag`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    skews = skews or {"side": 0.0, "diag": 0.012}
    sim = simulate(seed=seed, shots=shots)
    cams = {cid: camera_looking_at(cid, **spec) for cid, spec in DEFAULT_CAMERAS.items()}
    truth = {
        "synthetic": True,
        "seed": seed,
        "fps": fps,
        "cameras": {},
        "track": [{"t_s": r["t_s"], "xyz_m": r["xyz_m"]} for r in sim["track"][:: int(round(0.01 / sim["dt_s"]))]],
        "bounces": sim["bounces"],
        "hits": sim["hits"],
        "serve": sim["serve"],
        "dead": sim["dead"],
    }
    for cid, cam in cams.items():
        per = render(sim, cam, out_dir / f"{cid}.mp4", fps=fps, skew_s=skews[cid], seed=seed)
        blurball_like_json(
            per, out_dir / f"{cid}-blurball-like.json", noise_px=1.5, miss_p=0.08, false_p=0.05, seed=seed
        )
        truth["cameras"][cid] = {**cam.to_json(), "video": f"{cid}.mp4", **per}
    (out_dir / "truth.json").write_text(json.dumps(truth), encoding="utf8")
    return truth


def sample_frames(sim: dict, cam: Camera, fps: float = 30.0, skew_s: float = 0.0) -> dict:
    """Per-frame truth for a camera without rendering video (what `render` returns, minus the pixels)."""
    t_end = sim["track"][-1]["t_s"]
    frames = []
    k = 0
    while k / fps + skew_s <= t_end:
        t = k / fps + skew_s
        xyz = truth_at(sim, t)
        if xyz is not None and t >= sim["serve"]["release"]["t_s"] - 0.3:
            depth = float((cam.R @ xyz + cam.t)[2])
            r_px = max(1.5, cam.K[0, 0] * BALL_RADIUS_M / depth)
            frames.append(
                {"frame": k, "t_s": t, "xyz_m": xyz.tolist(), "xy_px": cam.project(xyz)[0].tolist(), "r_px": r_px}
            )
        else:
            frames.append({"frame": k, "t_s": t, "xyz_m": None, "xy_px": None, "r_px": None})
        k += 1
    return {"fps": fps, "skew_s": skew_s, "frames": frames, "corners_px": cam.project(CORNERS_M).tolist()}

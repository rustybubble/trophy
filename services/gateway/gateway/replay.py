"""Authenticated replay and Watch routes over the local recorder archive."""

from __future__ import annotations

import asyncio
import json
import math
import re
import subprocess
from urllib.parse import quote

import httpx
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from trophy.recordings import RecordingStore, safe_id

from .config import Settings
from .tokens import Claims, TokenError, verify


def project_mark(mark: dict, calibration: dict, default_t: float) -> dict | None:
    """Project plane geometry and its covariance with the inverse-homography Jacobian.

    3D bounce marks require an undistorted pinhole pose; a tabletop H alone cannot project height.
    """
    pos = np.array(mark["pos_m"], dtype=float)
    if pos.size < 2 or not np.isfinite(pos).all():
        raise ValueError("invalid bounce position")
    if pos.size == 3 and abs(pos[2]) > 1e-6:
        if not all(k in calibration for k in ("K", "rvec", "tvec")) or any(calibration.get("dist", [])):
            return None
        rv = np.array(calibration["rvec"], dtype=float)
        theta = np.linalg.norm(rv)
        axis = rv / theta if theta else np.zeros(3)
        x, y, z = axis
        skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
        rotation = np.eye(3) + math.sin(theta) * skew + (1 - math.cos(theta)) * (skew @ skew)
        K = np.array(calibration["K"]).reshape(3, 3)
        camera = rotation @ pos + np.array(calibration["tvec"])
        if camera[2] <= 0:
            return None
        homogeneous = K @ camera
        px = homogeneous[:2] / homogeneous[2]
        derivative = (K[:2] * homogeneous[2] - homogeneous[:2, None] * K[2]) / homogeneous[2] ** 2
        jacobian = derivative @ rotation
    else:
        H = np.linalg.inv(np.array(calibration["H_img_to_field"], dtype=float).reshape(3, 3))
        q = H @ np.array([pos[0], pos[1], 1])
        if abs(q[2]) < 1e-12:
            return None
        px = q[:2] / q[2]
        jacobian = (H[:2, :2] * q[2] - q[:2, None] * H[2, :2]) / q[2] ** 2
    raw = mark.get("cov_m2")
    if raw is not None:
        covariance = np.array(raw, dtype=float)
        if covariance.size == 9:
            covariance = covariance.reshape(3, 3)
            if jacobian.shape[1] == 2:
                covariance = covariance[:2, :2]
        elif covariance.size == 4:
            covariance = covariance.reshape(2, 2)
            jacobian = jacobian[:, :2]
        else:
            raise ValueError("bounce covariance must be 2x2 or 3x3")
    else:
        sigma = float(mark.get("sigma_m", 0))
        if not math.isfinite(sigma) or sigma < 0:
            raise ValueError("invalid bounce sigma")
        covariance = np.eye(jacobian.shape[1]) * sigma**2
    if (
        not np.isfinite(covariance).all()
        or not np.allclose(covariance, covariance.T)
        or np.linalg.eigvalsh(covariance).min() < -1e-12
    ):
        raise ValueError("invalid covariance")
    values, vectors = np.linalg.eigh(jacobian @ covariance @ jacobian.T)
    order = np.argsort(values)[::-1]
    radii = np.sqrt(np.maximum(0, values[order]))
    vector = vectors[:, order[0]]
    if not np.isfinite(px).all():
        return None
    return {
        "t_game_s": mark.get("t_game_s", default_t),
        "px": px.tolist(),
        "ellipse_px": {
            "cx": float(px[0]),
            "cy": float(px[1]),
            "rx": float(radii[0]),
            "ry": float(radii[1]),
            "angle_rad": math.atan2(float(vector[1]), float(vector[0])),
        },
    }


def replay_router(st: Settings) -> APIRouter:
    router = APIRouter(prefix="/api")
    store = RecordingStore(st.data_dir / "recordings")

    def authorize(request: Request, game: str, service: bool = False) -> tuple[Claims, str]:
        try:
            safe_id(game)
        except ValueError:
            raise HTTPException(404, "no such recording") from None
        header = request.headers.get("authorization", "")
        token = header[7:] if header.startswith("Bearer ") else request.query_params.get("token", "")
        if not token:
            raise HTTPException(401, "missing token")
        try:
            claims = verify(st.token_secret, token)
        except TokenError as exc:
            raise HTTPException(401, str(exc)) from None
        if claims.game_id != game and not (claims.has("service") and claims.game_id == "*"):
            raise HTTPException(403, "token belongs to another game")
        if service and not claims.has("service"):
            raise HTTPException(403, "engine service token required")
        return claims, token

    async def work(fn, *args):
        try:
            return await asyncio.to_thread(fn, *args)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None
        except (ValueError, KeyError, np.linalg.LinAlgError) as exc:
            raise HTTPException(422, str(exc)) from None
        except (subprocess.SubprocessError, RuntimeError):
            raise HTTPException(503, "replay processing unavailable; inspect local service logs") from None

    def window(t0: float, t1: float) -> None:
        if not math.isfinite(t0) or not math.isfinite(t1) or t0 < 0 or t1 <= t0 or t1 - t0 > 30:
            raise HTTPException(422, "window must be finite, increasing and at most 30 seconds")

    async def state_rows(request: Request, table: str, game: str, key: str | None = None) -> list[dict]:
        # All table/column names are constants and values were validated by safe_id.
        token = request.app.state.stdb_read_token
        if token is None:
            response = await request.app.state.http.post(f"{st.stdb_http}/v1/identity")
            response.raise_for_status()
            token = response.json()["token"]
            request.app.state.stdb_read_token = token
        sql = f"SELECT * FROM {table} WHERE game_id = '{game}'"
        if key:
            safe_id(key)
            sql += f" AND call_id = '{key}'"
        response = await request.app.state.http.post(
            f"{st.stdb_http}/v1/database/{st.stdb_module}/sql",
            content=sql,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "text/plain"},
        )
        response.raise_for_status()
        result = response.json()[0]
        names = [
            c["name"].get("some") if isinstance(c["name"], dict) else c["name"] for c in result["schema"]["elements"]
        ]
        return [json.loads(dict(zip(names, row, strict=True))["json"]) for row in result["rows"]]

    @router.get("/replay/{game}/clip")
    async def clip(request: Request, game: str, cam: str, t0: float, t1: float):
        authorize(request, game)
        window(t0, t1)
        path = await work(store.clip, game, cam, t0, t1)
        return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "private, max-age=3600"})

    @router.get("/replay/{game}/frames")
    async def frames(request: Request, game: str, cam: str, t0: float, t1: float, n: int = 4, crop: str | None = None):
        authorize(request, game, service=True)
        window(t0, t1)
        box = None
        if crop:
            try:
                box = tuple(int(x) for x in crop.split(","))
                if len(box) != 4:
                    raise ValueError
            except ValueError:
                raise HTTPException(422, "crop must be x,y,w,h in source pixels") from None
        return await work(store.frames, game, cam, t0, t1, n, box)

    @router.get("/replay/{game}/overlay")
    async def overlay(request: Request, game: str, cam: str, t0: float, t1: float, call_id: str | None = None):
        authorize(request, game)
        window(t0, t1)
        await work(store.meta, game, cam)
        ball = await work(store.rows, game, cam, "tracks_ball.jsonl", t0, t1)
        players = await work(store.rows, game, cam, "tracks_players.jsonl", t0, t1)
        rendered = [{"t_game_s": row["t_game_s"], "ball_px": row.get("px")} for row in ball]
        rendered += [{"t_game_s": row["t_game_s"], "players": row.get("players", [])} for row in players]
        rendered.sort(key=lambda row: row["t_game_s"])
        warnings, marks, lines = [], [], []
        path = store.camera(game, cam) / "calibration.json"
        calibration = json.loads(path.read_text()) if path.exists() else None
        if calibration is None:
            raw = await request.app.state.r.get(f"calib:{safe_id(cam)}")
            calibration = json.loads(raw) if raw else None
        if calibration and (calibration.get("game_id") != game or calibration.get("cam_id") != cam):
            calibration = None
        if calibration:
            lines = calibration.get("overlay_px", [])
        if call_id:
            try:
                calls = await state_rows(request, "call", game, call_id)
            except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
                raise HTTPException(503, "call metadata unavailable") from None
            if not calls:
                raise HTTPException(404, "no such call in game")
            call = calls[0]
            evidence_cams = {item["cam_id"] for item in call.get("evidence", [])}
            if evidence_cams and cam not in evidence_cams:
                warnings.append("call has no evidence from this camera")
            elif calibration:
                for mark in call.get("overlay", {}).get("bounce_marks", []):
                    t = mark.get("t_game_s", call["t_game_s"])
                    if t0 <= t <= t1:
                        projected = await work(project_mark, mark, calibration, call["t_game_s"])
                        if projected:
                            marks.append(projected)
                        else:
                            warnings.append("mark cannot be projected with available calibration")
        if not calibration:
            warnings.append("camera calibration unavailable")
        elif not calibration.get("trusted", False):
            warnings.append("camera calibration is untrusted; projected marks are illustrative")
        return {"frames": rendered, "marks": marks, "lines_px": lines, "warnings": warnings}

    @router.get("/watch/{game}/manifest")
    async def manifest(request: Request, game: str):
        _, token = authorize(request, game)
        base = store.camera(game, "scope-check").parent
        if not base.is_dir():
            raise HTTPException(404, "no recording for this game")
        local = json.loads((base / "game.json").read_text()) if (base / "game.json").exists() else {"game_id": game}
        game_row, scores = local, []
        try:
            games = await state_rows(request, "game", game)
            scores = await state_rows(request, "score", game)
            if games:
                game_row = games[0]
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
            pass  # the local manifest remains usable when live state is offline
        cams = []
        has_tracks = {"ball": False, "players": False}
        for directory in sorted(base.iterdir()):
            if not directory.is_dir() or not (directory / "meta.json").exists():
                continue
            meta = await work(store.meta, game, directory.name)
            prefix = f"/api/watch/{game}/hls/{directory.name}"
            suffix = f"?token={quote(token, safe='')}"
            cams.append(
                {
                    "cam_id": directory.name,
                    "hls_url": f"{prefix}/index.m3u8{suffix}",
                    "t0_game_s": meta["t0_game_s"],
                    "duration_s": meta["duration_s"],
                    "closed": meta["closed"],
                    "held_video_frames": meta.get("held_video_frames", 0),
                    "sprite": {
                        "url_template": f"{prefix}/sprite_{{n}}.jpg{suffix}",
                        "cols": 10,
                        "rows": 10,
                        "every_s": 2,
                        "w": 160,
                        "h": 90,
                    },
                }
            )
            for kind in has_tracks:
                file = directory / f"tracks_{kind}.jsonl"
                has_tracks[kind] |= file.exists() and file.stat().st_size > 0
        return {
            "game": game_row,
            "teams": game_row.get("teams", json.loads(local.get("teams_json", "[]"))),
            "final_score": scores if game_row.get("status") == "ended" else None,
            "duration_s": max((c["t0_game_s"] + c["duration_s"] for c in cams), default=0),
            "cams": cams,
            "has_tracks": has_tracks,
        }

    @router.get("/watch/{game}/hls/{cam}/{name}")
    async def asset(request: Request, game: str, cam: str, name: str):
        _, token = authorize(request, game)
        path = await work(store.asset, game, cam, name)
        if name.endswith(".m3u8"):
            suffix = f"?token={quote(token, safe='')}"
            lines = []
            for line in path.read_text().splitlines():
                if line.startswith("#EXT-X-MAP:"):
                    line = re.sub(r'URI="([^"]+)"', lambda m: f'URI="{m[1]}{suffix}"', line)
                elif line and not line.startswith("#"):
                    line += suffix
                lines.append(line)
            return Response(
                "\n".join(lines) + "\n",
                media_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"},
            )
        types = {".mp4": "video/mp4", ".m4s": "video/iso.segment", ".jpg": "image/jpeg", ".json": "application/json"}
        return FileResponse(path, media_type=types[path.suffix], headers={"Cache-Control": "private, max-age=2"})

    @router.get("/watch/{game}/tracks")
    async def tracks(request: Request, game: str, cam: str, kind: str = "ball", t0: float = 0, t1: float = 86400):
        authorize(request, game)
        if not all(math.isfinite(t) for t in (t0, t1)) or t0 < 0 or t1 < t0:
            raise HTTPException(422, "invalid track window")
        return await work(store.tracks, game, cam, kind, t0, t1)

    return router

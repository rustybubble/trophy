// Upload a clip, tap the four table corners on its first frame, and run it through the whole pipeline:
// flight (2D ball track + corner homography) -> the golden sport module -> the live engine over Redis -> Spacetime,
// so the calls land in the Calls panel like a live game's. The video plays in sync with the replay.
import { useEffect, useRef, useState } from "react";
import { ApiError, type Session } from "../lib/api.ts";

interface Upload {
  upload_id: string;
  game_id: string;
  name: string;
  bytes: number;
  width?: number;
  height?: number;
  fps?: number;
  frames?: number;
  duration_s?: number;
  frame_url: string;
  video_url: string;
}

interface Run {
  run_id: string;
  upload_id: string;
  status: "queued" | "tracking" | "playing" | "done" | "failed";
  stage: string;
  error?: string;
  speed: number;
  started_at_ms: number;
  play_started_at_ms?: number;
  finished_at_ms?: number;
  meta?: { samples: number; tracked_fraction: number | null; tracking_s: number; pose: string; fps: number };
  events?: number;
  log: string[];
}

const CORNER_NAMES = ["A end, right corner", "B end, right corner", "B end, left corner", "A end, left corner"];

async function api<T>(path: string, session: Session, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${session.token}`);
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function ClipPanel({ session }: { session: Session }) {
  const [upload, setUpload] = useState<Upload>();
  const [corners, setCorners] = useState<[number, number][]>([]);
  const [ball, setBall] = useState<"white" | "orange">("white");
  const [speed, setSpeed] = useState(1);
  const [run, setRun] = useState<Run>();
  const [busy, setBusy] = useState<string>();
  const [err, setErr] = useState<string>();
  const img = useRef<HTMLImageElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const tokenQ = `?token=${encodeURIComponent(session.token)}`;

  async function onFile(f: File | undefined) {
    if (!f) return;
    setErr(undefined);
    setRun(undefined);
    setCorners([]);
    setBusy("Uploading…");
    try {
      const up = await api<Upload>(`/demo/uploads?name=${encodeURIComponent(f.name)}`, session, {
        method: "POST",
        body: f,
        headers: { "Content-Type": f.type || "video/mp4" },
      });
      setUpload(up);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(undefined);
    }
  }

  function tap(e: React.MouseEvent<HTMLImageElement>) {
    const el = img.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * el.naturalWidth;
    const y = ((e.clientY - r.top) / r.height) * el.naturalHeight;
    const pt: [number, number] = [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
    setCorners((c) => (c.length >= 4 ? c : [...c, pt]));
  }

  async function start() {
    if (!upload || corners.length !== 4) return;
    setErr(undefined);
    setBusy("Starting…");
    const v = video.current; // unlock autoplay while we are inside the click
    if (v) {
      v.muted = true;
      void v
        .play()
        .then(() => v.pause())
        .catch(() => undefined);
    }
    try {
      const r = await api<Run>("/demo/runs", session, {
        method: "POST",
        body: JSON.stringify({ upload_id: upload.upload_id, corners, ball, speed }),
        headers: { "Content-Type": "application/json" },
      });
      setRun(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(undefined);
    }
  }

  // poll the run; start the video the moment the replay starts feeding the engine
  useEffect(() => {
    if (!run || run.status === "done" || run.status === "failed") return;
    const t = setInterval(() => {
      api<Run>(`/demo/runs/${run.run_id}`, session)
        .then((r) => {
          setRun(r);
          const v = video.current;
          if (r.status === "playing" && r.play_started_at_ms && v && v.paused) {
            v.currentTime = Math.max(0, (Date.now() - r.play_started_at_ms) / 1000) * r.speed;
            v.playbackRate = Math.min(4, Math.max(0.25, r.speed));
            void v.play().catch(() => undefined);
          }
        })
        .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
    }, 700);
    return () => clearInterval(t);
  }, [run?.run_id, run?.status, session]);

  return (
    <div className="panel clip">
      <h2>Upload a clip</h2>
      <p className="muted small">
        One phone, side-on at the net line, white ball. The clip is tracked (flight), the golden table-tennis module
        turns the track into bounces and dead balls, and the live engine calls the points into this game.
      </p>
      <div className="row">
        <input
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          disabled={!!busy}
          onChange={(e) => void onFile(e.target.files?.[0])}
        />
        {busy && <span className="muted small">{busy}</span>}
      </div>
      {err && <p className="bad">{err}</p>}
      {upload && !run && (
        <>
          <p className="small">
            <strong>{upload.name}</strong> · {upload.width}×{upload.height} @ {upload.fps?.toFixed(1)} fps ·{" "}
            {upload.duration_s?.toFixed(1)} s. Tap the four table corners:{" "}
            <strong>{corners.length < 4 ? CORNER_NAMES[corners.length] : "done"}</strong>
            {corners.length > 0 && (
              <button className="ghost small" onClick={() => setCorners([])}>
                reset
              </button>
            )}
          </p>
          <div className="frame">
            <img ref={img} src={upload.frame_url + tokenQ} alt="first frame" onClick={tap} />
            {corners.map(([x, y], i) => (
              <span
                key={i}
                className="corner"
                style={{
                  left: `${(x / (upload.width ?? 1)) * 100}%`,
                  top: `${(y / (upload.height ?? 1)) * 100}%`,
                }}
              >
                {["AR", "BR", "BL", "AL"][i]}
              </span>
            ))}
          </div>
          <div className="row">
            <label className="small">
              Ball{" "}
              <select value={ball} onChange={(e) => setBall(e.target.value as "white" | "orange")}>
                <option value="white">white</option>
                <option value="orange">orange</option>
              </select>
            </label>
            <label className="small">
              Speed{" "}
              <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                <option value={1}>1× (real time)</option>
                <option value={2}>2×</option>
                <option value={4}>4×</option>
              </select>
            </label>
            <button className="primary" disabled={corners.length !== 4 || !!busy} onClick={() => void start()}>
              Referee this clip
            </button>
          </div>
        </>
      )}
      {upload && (
        <video
          ref={video}
          src={upload.video_url + tokenQ}
          controls
          muted
          playsInline
          preload="auto"
          className="clipvideo"
          style={{ display: run ? "block" : "none" }}
        />
      )}
      {upload && run && (
        <>
          <p className="small">
            <span className={`badge ${run.status === "failed" ? "bad" : run.status === "done" ? "ok" : "warn"}`}>
              {run.status}
            </span>{" "}
            {run.stage}
            {run.meta && (
              <>
                {" "}
                · {run.meta.samples} ball samples
                {run.meta.tracked_fraction != null && (
                  <> ({Math.round(run.meta.tracked_fraction * 100)} % of frames)</>
                )}{" "}
                · tracked in {run.meta.tracking_s} s · {run.meta.pose}
              </>
            )}
            {run.events != null && <> · {run.events} events</>}
          </p>
          {run.error && <p className="bad">{run.error}</p>}
          {run.log.length > 0 && <pre className="log small muted">{run.log.slice(-6).join("\n")}</pre>}
          <p className="muted small">
            Calls appear in the Calls panel as the engine makes them. Calibration is four tapped corners on one camera
            with no clock sync, so every call here is at most BETA and nothing is a measurement of accuracy.
          </p>
          <button
            className="ghost"
            onClick={() => {
              setRun(undefined);
              setCorners([]);
            }}
          >
            Run again
          </button>
        </>
      )}
    </div>
  );
}

// Recorded clips as live cameras. Add any number of clips (angles of the same moment, or takes from one camera
// position), check the table corners on each first frame (pre-filled by the tabletop detector), then Go live: every
// clip joins the game as a camera phone and streams in real time, BlurBall runs on each frame as it arrives, the golden
// sport module turns the tracks into bounces and dead balls, and the engine calls the points into this game.
import { useEffect, useRef, useState } from "react";
import { ApiError, type Session } from "../lib/api.ts";

interface Upload {
  upload_id: string;
  name: string;
  width: number;
  height: number;
  fps: number;
  duration_s?: number;
  recorded_at_ms?: number | null;
  device?: string | null;
  frame_url: string;
  suggested_corners_norm?: [number, number][] | null;
  corner_suggestion?: { agreeing_frames: number; max_spread_px: number } | null;
}

interface Clip extends Upload {
  corners: [number, number][]; // normalised 0..1 on the streamed frame
  auto: boolean; // corners came from the detector
}

interface LiveCam {
  cam_id?: string;
  clips?: string[];
  frames?: number;
  lag_max_ms?: number;
  reproj_px?: number;
  now_playing?: string;
  seconds?: number;
}

interface Live {
  live_id: string;
  status: "starting" | "streaming" | "done" | "failed";
  mode: "simultaneous" | "sequential";
  mode_reason: string;
  speed: number;
  wall0_ms?: number;
  clips: { upload_id: string; label: string; name: string; duration_s?: number; offset_s: number }[];
  cameras: Record<string, LiveCam>;
  error?: string;
}

const CORNER_NAMES = ["near end A (left)", "near end B (right)", "far end B (right)", "far end A (left)"];
const SHORT = ["A·near", "B·near", "B·far", "A·far"];

async function api<T>(path: string, s: Session, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${s.token}`);
  const res = await fetch(`/api${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = (await res.json()) as { detail?: unknown };
      detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail ?? b);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

function fmtTime(ms?: number | null): string {
  return ms ? new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "?";
}

/** A camera's live frames, as the referee sees them, with BlurBall's detection on that frame. */
function CameraLive({ session, label, cam }: { session: Session; label: string; cam: LiveCam }) {
  const [src, setSrc] = useState<string>();
  const [ball, setBall] = useState<{ x: number; y: number; p: number } | null>(null);
  const [info, setInfo] = useState("");
  useEffect(() => {
    if (!cam.cam_id) return;
    let stop = false;
    let url: string | undefined;
    const tick = async () => {
      while (!stop) {
        const t0 = performance.now();
        try {
          const res = await fetch(`/api/demo/cams/${cam.cam_id}/live`, {
            headers: { Authorization: `Bearer ${session.token}` },
            cache: "no-store",
          });
          if (res.ok) {
            const b = res.headers.get("X-Ball") ?? "none";
            const [x, y, p] = b === "none" ? [] : b.split(",").map(Number);
            setBall(x !== undefined ? { x: x!, y: y!, p: p! } : null);
            const lag = res.headers.get("X-Ball-Lag-Frames");
            setInfo(
              `t ${Number(res.headers.get("X-T-Game")).toFixed(1)} s · BlurBall ${lag ? `${lag} frames behind` : "…"}`,
            );
            const blob = await res.blob();
            const next = URL.createObjectURL(blob);
            setSrc(next);
            if (url) URL.revokeObjectURL(url);
            url = next;
          }
        } catch {
          /* the next tick retries */
        }
        await new Promise((r) => setTimeout(r, Math.max(0, 110 - (performance.now() - t0))));
      }
    };
    void tick();
    return () => {
      stop = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [cam.cam_id, session.token]);
  return (
    <div className="camlive">
      <div className="frame">
        {src ? (
          <img src={src} alt={`${label} live`} />
        ) : (
          <div className="placeholder muted small">waiting for frames…</div>
        )}
        {ball && (
          <span
            className="ball"
            style={{ left: `${(ball.x / 1280) * 100}%`, top: `${(ball.y / 720) * 100}%` }}
            title={`BlurBall p=${ball.p.toFixed(2)} (uncalibrated)`}
          />
        )}
        <span className="camtag">{label}</span>
      </div>
      <div className="muted small">
        {cam.now_playing ?? "…"} · {cam.frames ?? 0} frames sent
        {cam.lag_max_ms != null && ` · max send lag ${cam.lag_max_ms} ms`}
        {info && ` · ${info}`}
      </div>
    </div>
  );
}

export function LiveClipsPanel({ session }: { session: Session }) {
  const [clips, setClips] = useState<Clip[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [mode, setMode] = useState<"auto" | "simultaneous" | "sequential">("auto");
  const [speed, setSpeed] = useState(1);
  const [live, setLive] = useState<Live>();
  const [busy, setBusy] = useState<string>();
  const [err, setErr] = useState<string>();
  const img = useRef<HTMLImageElement>(null);
  const tokenQ = `?token=${encodeURIComponent(session.token)}`;

  async function add(files: FileList | null) {
    if (!files?.length) return;
    setErr(undefined);
    for (const f of Array.from(files)) {
      setBusy(`Uploading ${f.name} (${(f.size / 1e6).toFixed(0)} MB) and preparing it…`);
      try {
        const up = await api<Upload>(`/demo/uploads?name=${encodeURIComponent(f.name)}`, session, {
          method: "POST",
          body: f,
          headers: {
            "Content-Type": f.type || (f.name.toLowerCase().endsWith(".mov") ? "video/quicktime" : "video/mp4"),
          },
        });
        const corners = up.suggested_corners_norm ?? [];
        setClips((c) => [...c, { ...up, corners, auto: corners.length === 4 }]);
        if (corners.length !== 4) setEditing(clips.length);
      } catch (e) {
        setErr(`${f.name}: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
    setBusy(undefined);
  }

  function tap(e: React.MouseEvent<HTMLImageElement>, i: number) {
    const el = img.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const pt: [number, number] = [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
    setClips((cs) =>
      cs.map((c, j) => {
        if (j !== i || c.corners.length >= 4) return c;
        const corners = [...c.corners, pt];
        if (corners.length === 4) setEditing(null);
        return { ...c, corners, auto: false };
      }),
    );
  }

  async function goLive() {
    setErr(undefined);
    setBusy("Going live…");
    try {
      const l = await api<Live>("/demo/live", session, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clips: clips.map((c) => ({ upload_id: c.upload_id, corners_norm: c.corners })),
          mode,
          speed,
        }),
      });
      setLive(l);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(undefined);
    }
  }

  useEffect(() => {
    if (!live || live.status === "done" || live.status === "failed") return;
    const t = setInterval(() => {
      api<Live>(`/demo/live/${live.live_id}`, session)
        .then(setLive)
        .catch((e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
    }, 1000);
    return () => clearInterval(t);
  }, [live?.live_id, live?.status, session]);

  const ready = clips.length > 0 && clips.every((c) => c.corners.length === 4) && !busy;
  const editingClip = editing != null ? clips[editing] : undefined;

  return (
    <div className="panel liveclips">
      <h2>Recorded clips as live cameras</h2>
      <p className="muted small">
        Each clip joins this game as a camera phone and streams in real time. BlurBall finds the ball in every frame as
        it arrives, the table-tennis module turns the track into bounces and dead balls, and the engine calls the
        points. Clips recorded at the same time are angles of one moment; clips recorded one after another are takes
        from one camera and play back to back.
      </p>
      {!live && (
        <>
          <div className="row">
            <input
              type="file"
              multiple
              accept="video/mp4,video/quicktime,video/webm,.mov,.MOV"
              disabled={!!busy}
              onChange={(e) => void add(e.target.files)}
            />
          </div>
          {busy && <p className="muted small">{busy}</p>}
          {clips.length > 0 && (
            <ol className="cliplist">
              {clips.map((c, i) => (
                <li key={c.upload_id}>
                  <img
                    className="thumb"
                    src={c.frame_url + tokenQ}
                    alt=""
                    onClick={() => {
                      setEditing(i);
                    }}
                  />
                  <div>
                    <strong>{c.name}</strong>
                    <div className="muted small">
                      {c.width}×{c.height} @ {c.fps.toFixed(0)} fps · {c.duration_s?.toFixed(1)} s · recorded{" "}
                      {fmtTime(c.recorded_at_ms)}
                      {c.device && ` · ${c.device}`}
                    </div>
                    <div className="small">
                      {c.corners.length === 4 ? (
                        <span className="ok">
                          Table set
                          {c.auto && c.corner_suggestion
                            ? ` automatically (${c.corner_suggestion.agreeing_frames} frames agree)`
                            : ""}
                        </span>
                      ) : (
                        <span className="warn">Tap the table corners</span>
                      )}{" "}
                      <button
                        className="ghost small"
                        onClick={() => {
                          setClips((cs) => cs.map((x, j) => (j === i ? { ...x, corners: [], auto: false } : x)));
                          setEditing(i);
                        }}
                      >
                        retap
                      </button>
                      <button className="ghost small" onClick={() => setClips((cs) => cs.filter((_, j) => j !== i))}>
                        remove
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
          {editingClip && editing != null && (
            <>
              <p className="small">
                <strong>{editingClip.name}</strong>:{" "}
                {editingClip.corners.length < 4
                  ? `tap the ${CORNER_NAMES[editingClip.corners.length]} corner of the table top`
                  : "corners set (click retap to redo)"}
              </p>
              <div className="frame">
                <img
                  ref={img}
                  src={editingClip.frame_url + tokenQ}
                  alt="first frame"
                  onClick={(e) => tap(e, editing)}
                />
                {editingClip.corners.map(([x, y], k) => (
                  <span key={k} className="corner" style={{ left: `${x * 100}%`, top: `${y * 100}%` }}>
                    {SHORT[k]}
                  </span>
                ))}
              </div>
            </>
          )}
          {clips.length > 0 && (
            <div className="row">
              <label className="small">
                Cameras{" "}
                <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
                  <option value="auto">auto (from the recording times)</option>
                  <option value="simultaneous">angles of the same moment</option>
                  <option value="sequential">takes from one camera, back to back</option>
                </select>
              </label>
              <label className="small">
                Speed{" "}
                <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                  <option value={1}>1× (real time)</option>
                  <option value={2}>2×</option>
                </select>
              </label>
              <button className="primary" disabled={!ready} onClick={() => void goLive()}>
                Go live
              </button>
            </div>
          )}
        </>
      )}
      {err && <p className="bad">{err}</p>}
      {live && (
        <>
          <p className="small">
            <span className={`badge ${live.status === "failed" ? "bad" : live.status === "done" ? "ok" : "warn"}`}>
              {live.status === "streaming" ? "LIVE" : live.status}
            </span>{" "}
            {live.mode === "simultaneous" ? "angles of the same moment" : "takes from one camera, back to back"}:{" "}
            <span className="muted">{live.mode_reason}</span>
          </p>
          <div className="camgrid">
            {Object.entries(live.cameras).map(([label, cam]) => (
              <CameraLive key={label} session={session} label={label} cam={cam} />
            ))}
          </div>
          {live.error && <p className="bad">{live.error}</p>}
          <p className="muted small">
            The corners are tapped, not auto-checked, so calibration is untrusted and every call is BETA at most.
            BlurBall scores are uncalibrated. No accuracy is claimed on these clips: they are unlabelled.
          </p>
          {(live.status === "done" || live.status === "failed") && (
            <button className="ghost" onClick={() => setLive(undefined)}>
              Stream again
            </button>
          )}
        </>
      )}
    </div>
  );
}

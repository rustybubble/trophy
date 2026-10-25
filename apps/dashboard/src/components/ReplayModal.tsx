// Instant replay of a call from the referee's own recording (the recorder's HLS archive of every camera, cut by
// the gateway's /api/replay/{game}/clip), with the call's bounce marks and their σ ellipses projected onto the frame
// by /api/replay/{game}/overlay. The judge watches it here while the phones show the same window; the AI second
// opinion (uncalibrated) sits next to it. Nothing is generated: the clip is the camera's frames, the marks are the
// engine's measurements.
import { useEffect, useMemo, useRef, useState } from "react";
import type { AiVote, Call, Camera } from "@trophy/state-client";
import { replayClipUrl, replayOverlay, type Overlay, type Session } from "../lib/api.ts";

const TIER_TEXT = { AUTO: "AUTO", BETA: "BETA", PLAYERS: "PLAYERS DECIDE" } as const;
const RATES = [1, 0.5, 0.25];
const W = 1280;
const H = 720;

/** The window the replay shows: the call's evidence ± 1 s, else the 3 s before the call and 1 s after. */
export function replayWindow(call: Call): { t0: number; t1: number; camIds: string[] } {
  const ev = call.evidence ?? [];
  const t0 = Math.max(0, (ev.length ? Math.min(...ev.map((e) => e.t0_s)) : call.t_game_s - 3) - 1);
  const t1 = (ev.length ? Math.max(...ev.map((e) => e.t1_s)) : call.t_game_s) + 1;
  return { t0, t1: Math.min(t1, t0 + 30), camIds: [...new Set(ev.map((e) => e.cam_id))] };
}

export function ReplayModal({
  call,
  cameras,
  votes,
  session,
  onClose,
}: {
  call: Call;
  cameras: Camera[];
  votes: AiVote[];
  session: Session;
  onClose: () => void;
}) {
  const win = useMemo(() => replayWindow(call), [call]);
  // every camera phone of the game, the ones the call cites first
  const cams = useMemo(() => {
    const all = cameras.filter((c) => c.role.split(",").includes("cam"));
    return [...all].sort((a, b) => Number(win.camIds.includes(b.cam_id)) - Number(win.camIds.includes(a.cam_id)));
  }, [cameras, win.camIds]);
  const [camId, setCamId] = useState<string>();
  const active = camId ?? cams[0]?.cam_id;
  const [src, setSrc] = useState<string>();
  const [overlay, setOverlay] = useState<Overlay>();
  const [status, setStatus] = useState("");
  const [rate, setRate] = useState(0.5);
  const video = useRef<HTMLVideoElement>(null);

  // the clip: the recorder finalizes 2 s segments, so a window that ends at the call can take a few seconds
  useEffect(() => {
    if (!active) return;
    let stop = false;
    let url: string | undefined;
    setSrc(undefined);
    setOverlay(undefined);
    const t0 = Date.now();
    const poll = async () => {
      while (!stop && Date.now() - t0 < 30_000) {
        try {
          const res = await fetch(replayClipUrl(session, active, win.t0, win.t1));
          if (res.ok) {
            url = URL.createObjectURL(await res.blob());
            if (!stop) {
              setSrc(url);
              setStatus("");
            }
            return;
          }
          setStatus(
            res.status === 404 ? `Cutting the replay… ${Math.round((Date.now() - t0) / 1000)} s` : `${res.status}`,
          );
        } catch {
          setStatus("Replay unavailable");
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
      if (!stop && !url) setStatus("No recording of this window (the recorder was not running, or the game is older)");
    };
    void poll();
    void replayOverlay(session, active, win.t0, win.t1, call.id)
      .then((o) => !stop && setOverlay(o))
      .catch(() => undefined);
    return () => {
      stop = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [active, session, win.t0, win.t1, call.id]);

  useEffect(() => {
    const v = video.current;
    if (!v || !src) return;
    v.playbackRate = rate;
    void v.play().catch(() => undefined);
  }, [src, rate]);

  const step = (dir: number) => {
    const v = video.current;
    if (!v) return;
    v.pause();
    v.currentTime = Math.max(0, v.currentTime + dir / 30);
  };
  const mine = votes.filter((v) => v.call_id === call.id);

  return (
    <div className="modal-wrap" onClick={onClose} role="dialog" aria-label="Instant replay">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="row">
          <span className={`tier ${call.tier}`}>{TIER_TEXT[call.tier]}</span>
          <strong>{call.text}</strong>
          <span className="muted small">
            {call.rule_id}
            {call.tier !== "AUTO" && ` · p = ${call.p.toFixed(2)}`} · t {call.t_game_s.toFixed(1)} s · {call.status}
          </span>
          <button className="ghost" onClick={onClose}>
            Close
          </button>
        </div>
        {call.why && <p className="muted small why">{call.why}</p>}
        <div className="stage">
          {src ? (
            <video ref={video} key={src} src={src} playsInline muted loop controls={false} />
          ) : (
            <div className="placeholder muted">{status || "Loading…"}</div>
          )}
          {src && overlay && overlay.marks.length > 0 && (
            <svg viewBox={`0 0 ${W} ${H}`} className="marks" aria-hidden>
              {overlay.marks.map((m, i) => (
                <g
                  key={i}
                  transform={`rotate(${(m.ellipse_px.angle_rad * 180) / Math.PI} ${m.ellipse_px.cx} ${m.ellipse_px.cy})`}
                >
                  <ellipse
                    cx={m.ellipse_px.cx}
                    cy={m.ellipse_px.cy}
                    rx={Math.max(6, m.ellipse_px.rx)}
                    ry={Math.max(6, m.ellipse_px.ry)}
                  />
                </g>
              ))}
            </svg>
          )}
        </div>
        <div className="row">
          {cams.length > 1 &&
            cams.map((c) => (
              <button
                key={c.cam_id}
                className={c.cam_id === active ? "primary" : ""}
                onClick={() => setCamId(c.cam_id)}
              >
                {c.label || c.cam_id}
              </button>
            ))}
          {RATES.map((r) => (
            <button key={r} className={r === rate ? "primary" : ""} onClick={() => setRate(r)}>
              {r === 1 ? "1×" : r === 0.5 ? "½×" : "¼×"}
            </button>
          ))}
          <button onClick={() => step(-1)}>◀ frame</button>
          <button onClick={() => step(1)}>frame ▶</button>
          <button onClick={() => void video.current?.play()}>Play</button>
          <span className="muted small">
            {win.t0.toFixed(1)}–{win.t1.toFixed(1)} s · the referee's recording, 720p
            {overlay?.warnings.length ? ` · ${overlay.warnings.join("; ")}` : ""}
          </span>
        </div>
        {!!mine.length && (
          <table className="small">
            <tbody>
              {mine.map((v) => {
                const top = Object.entries(v.probs).sort((x, y) => y[1] - x[1])[0];
                return (
                  <tr key={v.backend}>
                    <td>{v.backend === "claude" ? "Claude" : "Geometry"}</td>
                    <td>{v.error ? <span className="bad">{v.error}</span> : (v.choice ?? top?.[0] ?? "—")}</td>
                    <td className="num">{top ? top[1].toFixed(2) : ""}</td>
                    <td className="muted">{v.rationale}</td>
                    <td className="muted small">uncalibrated</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// The Spacetime showcase (D-42): every replayed angle playing in sync from its `feed` row, every phone's drift from
// its `viewer` row, camera health and the ball each angle sees. Every number here arrives over Spacetime subscriptions.
import { useEffect, useRef, useState } from "react";
import type { Camera, Feed, TrackSample, Viewer } from "@trophy/state-client";
import {
  listScenarios,
  serverOffsetMs,
  startScenario,
  stopScenario,
  type ScenarioSummary,
  type Session,
} from "../lib/api.ts";

const SEEK_MS = 120; // seek when playback is further than this from the schedule; nudge the rate below it

function SyncedVideo({ feed, token, offsetMs }: { feed: Feed; token: string; offsetMs: number }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [drift, setDrift] = useState<number>();

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    const tick = () => {
      const want = feed.offset_s + (Date.now() + offsetMs - feed.wall0_ms) / 1000;
      if (feed.status !== "playing" || want < 0 || want > feed.duration_s + feed.offset_s) {
        if (!v.paused) v.pause();
        setDrift(undefined);
        return;
      }
      if (v.paused) void v.play().catch(() => undefined);
      const d = (v.currentTime - want) * 1000;
      if (Math.abs(d) > SEEK_MS) v.currentTime = want;
      else v.playbackRate = d > 20 ? 0.97 : d < -20 ? 1.03 : 1;
      setDrift(d);
    };
    const id = setInterval(tick, 250);
    tick();
    return () => clearInterval(id);
  }, [feed, offsetMs]);

  return (
    <figure className="angle">
      <video ref={ref} src={`${feed.video_url}?token=${encodeURIComponent(token)}`} muted playsInline preload="auto" />
      <figcaption>
        <strong>{feed.label}</strong>
        <span className="muted">
          {feed.status}
          {drift !== undefined && ` · ${drift >= 0 ? "+" : ""}${drift.toFixed(0)} ms`}
        </span>
      </figcaption>
    </figure>
  );
}

export function NetworkPanel({
  session,
  feeds,
  viewers,
  cameras,
  trail,
}: {
  session?: Session;
  feeds: Feed[];
  viewers: Viewer[];
  cameras: Camera[];
  trail: TrackSample[];
}) {
  const [offsetMs, setOffsetMs] = useState(0);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string>();
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    void serverOffsetMs()
      .then(setOffsetMs)
      .catch(() => undefined);
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (!session) return;
    void listScenarios(session)
      .then((s) => {
        setScenarios(s);
        setPick((p) => p || s.find((x) => x.ready)?.id || "");
      })
      .catch((e: unknown) => setErr(String(e instanceof Error ? e.message : e)));
  }, [session]);

  async function run(f: () => Promise<unknown>) {
    setBusy(true);
    setErr(undefined);
    try {
      await f();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const playing = feeds.some((f) => f.status === "playing");
  const credit = feeds.find((f) => f.credit)?.credit;
  const lastBall = (cam: string) => [...trail].reverse().find((s) => s.cam_id === cam);
  const camOf = (id: string) => cameras.find((c) => c.cam_id === id);
  const labelOf = (cam: string) => feeds.find((f) => f.cam_id === cam)?.label ?? cam;

  return (
    <div className="panel network">
      <div className="row between">
        <h2>Cameras in sync · SpacetimeDB</h2>
        {session && (
          <div className="row">
            <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Scenario" disabled={playing}>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id} disabled={!s.ready}>
                  {s.title}
                  {s.ready ? "" : " (media missing)"}
                </option>
              ))}
            </select>
            {playing ? (
              <button disabled={busy} onClick={() => void run(() => stopScenario(session))}>
                Stop
              </button>
            ) : (
              <button
                className="primary"
                disabled={busy || !pick}
                onClick={() => void run(() => startScenario(session, pick))}
              >
                {busy ? "Starting…" : "Go live"}
              </button>
            )}
          </div>
        )}
      </div>
      {err && <p className="bad">{err}</p>}
      {feeds.length > 0 && (
        <p className="muted small">
          Replayed feed: recorded footage streamed as if live.{credit ? ` Footage: ${credit}` : ""}
        </p>
      )}
      <div className="angles">
        {session && feeds.map((f) => <SyncedVideo key={f.cam_id} feed={f} token={session.token} offsetMs={offsetMs} />)}
      </div>
      {feeds.length > 0 && (
        <table className="small">
          <thead>
            <tr>
              <th>Angle</th>
              <th className="num">fps to referee</th>
              <th>ball</th>
              <th>calibration</th>
            </tr>
          </thead>
          <tbody>
            {feeds.map((f) => {
              const cam = camOf(f.cam_id);
              const ball = lastBall(f.cam_id);
              return (
                <tr key={f.cam_id}>
                  <td>{f.label}</td>
                  <td className="num">{cam ? cam.fps_in.toFixed(1) : "—"}</td>
                  <td className={ball ? "ok" : "muted"}>{ball ? `seen @ ${ball.t_game_s.toFixed(1)} s` : "—"}</td>
                  <td className={f.annotated ? "muted" : f.calibrated ? "warn" : "muted"}>
                    {f.annotated ? "annotated events" : f.calibrated ? "tapped corners (untrusted)" : "none"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <h3>Phones</h3>
      {!viewers.length && <p className="muted">No phones showing an angle yet. Scan the join code.</p>}
      <table className="small">
        <tbody>
          {viewers.map((v) => {
            const stale = now - v.last_seen_ms > 6000;
            const bad = Math.abs(v.drift_ms) > 120;
            return (
              <tr key={v.viewer_id}>
                <td className={v.connected && !stale ? "ok" : "bad"}>{v.connected && !stale ? "●" : "○"}</td>
                <td>{v.name || v.viewer_id}</td>
                <td>{labelOf(v.cam_id)}</td>
                <td className={`num ${bad ? "warn" : "ok"}`}>
                  {v.playing ? `${v.drift_ms >= 0 ? "+" : ""}${v.drift_ms.toFixed(0)} ms` : "paused"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="muted small">
        Each phone reads the same <code>feed</code> row and plays its angle at the scheduled server time, then reports
        its drift back as a <code>viewer</code> row.
      </p>
    </div>
  );
}

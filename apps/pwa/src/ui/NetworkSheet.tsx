import type { Camera, Feed, Observation, Viewer } from "@trophy/state-client";
import { fmtDrift, liveViewers, sortFeeds } from "../lib/demo.ts";
import type { TrackBuffer } from "../lib/useTrophy.ts";
import { Sheet } from "./Sheet.tsx";

const driftCls = (ms: number) => (Math.abs(ms) < 40 ? "drift-ok" : Math.abs(ms) < 120 ? "drift-warn" : "drift-bad");

// Regulation table (ITTF 2.1.2), field frame: metres, origin at the centre, x towards team B (interfaces-v1 §3).
const TABLE = { length: 2.74, width: 1.525 };
const W = 320;
const M = 0.35;
const S = W / (TABLE.length + 2 * M);
const H = Math.round((TABLE.width + 2 * M) * S);
const toPx = (x: number, y: number): [number, number] => [
  (x + TABLE.length / 2 + M) * S,
  (TABLE.width / 2 + M - y) * S,
];

/** A tiny top-down view drawn only from Spacetime observation rows (no video). */
function MiniWorld({ bounces }: { bounces: Observation[] }) {
  const [x0, y0] = toPx(-TABLE.length / 2, TABLE.width / 2);
  const [x1, y1] = toPx(TABLE.length / 2, -TABLE.width / 2);
  const [nx] = toPx(0, 0);
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} className="world" role="img" aria-label="Top-down table with recent bounces">
        <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} className="table" rx={2} />
        <line x1={x0} y1={(y0 + y1) / 2} x2={x1} y2={(y0 + y1) / 2} className="centre" />
        <line x1={nx} y1={y0 - 6} x2={nx} y2={y1 + 6} className="net" />
        <text x={x0} y={y1 + 14} className="lbl">
          A
        </text>
        <text x={x1 - 8} y={y1 + 14} className="lbl">
          B
        </text>
        {bounces.map((o, i) => {
          if (!o.pos_m) return null;
          const [x, y] = toPx(o.pos_m.x, o.pos_m.y);
          const fused = o.cams.length > 1;
          const r = Math.max(3.5, (o.sigma_m ?? 0.02) * S * 2);
          const color = fused ? "var(--accent)" : "var(--beta)";
          return (
            <circle
              key={o.id}
              cx={x}
              cy={y}
              r={r}
              fill={fused ? color : "none"}
              stroke={color}
              strokeWidth={2}
              opacity={1 - i / (bounces.length + 2)}
            />
          );
        })}
      </svg>
      <div className="legend">
        <span>
          <i style={{ background: "var(--accent)" }} />
          seen by 2+ angles (fused)
        </span>
        <span>
          <i style={{ border: "2px solid var(--beta)" }} />
          one angle
        </span>
        <span>circle size = 2σ</span>
      </div>
    </>
  );
}

/** The Spacetime showcase: every angle, every phone and its drift, and the fused observations, live. */
export function NetworkSheet(props: {
  feeds: Feed[];
  cameras: Camera[];
  viewers: Viewer[];
  observations: Observation[];
  track: TrackBuffer;
  meId: string;
  sport?: string;
  clock: { offsetMs: number | null; syncErrMs: number | null; connected: boolean } | undefined;
  reportError?: string;
  nowMs: number;
  onClose: () => void;
}) {
  const feeds = sortFeeds(props.feeds);
  const labelOf = (cam: string) => feeds.find((f) => f.cam_id === cam)?.label ?? cam;
  const phones = liveViewers(props.viewers, props.nowMs).sort((a, b) =>
    a.viewer_id === props.meId ? -1 : b.viewer_id === props.meId ? 1 : (a.name ?? "").localeCompare(b.name ?? ""),
  );
  const bounces = props.observations.filter((o) => o.type === "bounce").slice(0, 8);
  const maxDrift = phones.filter((p) => p.playing).reduce((m, p) => Math.max(m, Math.abs(p.drift_ms)), 0);

  return (
    <Sheet title="Network" onClose={props.onClose} tall>
      <div className="note">
        <span className="status-dot ok" /> Every device reads the same Spacetime tables
      </div>

      <section className="section">
        <h3>Angles</h3>
        {feeds.length ? (
          <table className="tbl">
            <thead>
              <tr>
                <th>Angle</th>
                <th>Feed</th>
                <th className="num">fps in</th>
                <th style={{ paddingLeft: 12 }}>Ball</th>
                <th className="num">Phones</th>
              </tr>
            </thead>
            <tbody>
              {feeds.map((f) => {
                const cam = props.cameras.find((c) => c.cam_id === f.cam_id);
                const seen = props.track.lastSeen.get(f.cam_id);
                const ball = seen !== undefined && Date.now() - seen < 2000;
                const n = phones.filter((p) => p.cam_id === f.cam_id).length;
                return (
                  <tr key={f.cam_id}>
                    <td>
                      <b>{f.label}</b>
                      {f.annotated && <div className="small muted">annotated</div>}
                    </td>
                    <td>
                      <span className="small">{f.status}</span>
                    </td>
                    <td className="num">
                      <span
                        className={`status-dot ${cam?.connected ? "ok" : "bad"}`}
                        style={{ display: "inline-block", marginRight: 6, width: 8, height: 8 }}
                      />
                      {cam ? cam.fps_in.toFixed(1) : "—"}
                    </td>
                    <td style={{ paddingLeft: 12 }}>
                      {ball ? <span className="drift-ok">seen</span> : <span className="muted">—</span>}
                    </td>
                    <td className="num">{n}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p className="small muted">No scenario is live. The host picks one from the ⋯ menu.</p>
        )}
      </section>

      <section className="section">
        <h3>Phones{phones.length ? ` · max drift ${Math.round(maxDrift)} ms` : ""}</h3>
        {phones.length ? (
          <table className="tbl">
            <thead>
              <tr>
                <th>Phone</th>
                <th>Angle</th>
                <th className="num">Drift</th>
              </tr>
            </thead>
            <tbody>
              {phones.map((p) => (
                <tr key={p.viewer_id} className={p.viewer_id === props.meId ? "me" : ""}>
                  <td>
                    {p.name || p.viewer_id}
                    {p.viewer_id === props.meId ? " (you)" : ""}
                  </td>
                  <td>{labelOf(p.cam_id)}</td>
                  <td className={`num ${p.playing ? driftCls(p.drift_ms) : "muted"}`}>
                    {p.playing ? fmtDrift(p.drift_ms) : "paused"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="small muted">No phones are reporting yet.</p>
        )}
        {props.reportError && <p className="small err">This phone can't report its drift: {props.reportError}</p>}
        {props.clock && (
          <p className="small muted">
            Clock: {props.clock.connected ? "synced to the referee laptop" : "connecting…"}
            {props.clock.offsetMs !== null ? ` · offset ${props.clock.offsetMs.toFixed(1)} ms` : ""}
            {props.clock.syncErrMs !== null ? ` ± ${props.clock.syncErrMs.toFixed(1)} ms` : ""}
          </p>
        )}
      </section>

      <section className="section">
        <h3>Fused observations</h3>
        {(!props.sport || props.sport === "table_tennis") && <MiniWorld bounces={bounces} />}
        {bounces.length ? (
          <table className="tbl">
            <tbody>
              {bounces.slice(0, 5).map((o) => (
                <tr key={o.id}>
                  <td className="num" style={{ textAlign: "left" }}>
                    {o.t_game_s.toFixed(1)} s
                  </td>
                  <td>bounce{o.side ? ` · ${o.side}` : ""}</td>
                  <td>
                    <span className="cams">
                      {o.cams.map((c) => (
                        <span key={c} className="tag">
                          {labelOf(c)}
                        </span>
                      ))}
                    </span>
                  </td>
                  <td className="num">σ {o.sigma_m !== undefined ? `${(o.sigma_m * 1000).toFixed(0)} mm` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="small muted">No bounces yet.</p>
        )}
      </section>
    </Sheet>
  );
}

import type { AiVote, Call, Commentary, Moment, Observation } from "@trophy/state-client";

const TIER = { AUTO: "AUTO", BETA: "BETA", PLAYERS: "PLAYERS DECIDE" } as const;
const BACKENDS: AiVote["backend"][] = ["geometry", "claude"];

/** The call behind the moment being replayed: tier, p, why, the AI second opinion (uncalibrated), the serve-toss
 *  trace for serve calls, and any commentary lines. */
export function ReplayCard({
  moment,
  call,
  votes,
  observations,
  commentary,
}: {
  moment?: Moment;
  call?: Call;
  votes: AiVote[];
  observations: Observation[];
  commentary: Commentary[];
}) {
  if (!moment) {
    return (
      <div className="panel">
        <h2>Replay</h2>
        <p className="muted">Pick a moment to see its call, the AI second opinion and the evidence.</p>
      </div>
    );
  }
  const mine = call ? votes.filter((v) => v.call_id === call.id) : [];
  const tossId = call?.overlay?.serve_toss_event_id;
  const toss = tossId ? observations.find((o) => o.id === tossId) : undefined;
  return (
    <div className="panel">
      <h2>Replay{moment.is_best_play && <span className="badge best">★ Play of the game</span>}</h2>
      <div className="title">{moment.label}</div>
      {!!moment.reasons.length && <div className="muted small">Why it's here: {moment.reasons.join(" · ")}</div>}
      {call && (
        <div className="call">
          <span className={`tier ${call.tier}`}>{TIER[call.tier]}</span> {call.text}
          <div className="muted small">
            {call.rule_id}
            {call.tier !== "AUTO" && ` · p = ${call.p.toFixed(2)}`} · {call.status}
            {call.why && ` · ${call.why}`}
          </div>
        </div>
      )}
      {!!mine.length && (
        <>
          <h3>
            AI second opinion <span className="badge">uncalibrated</span>
          </h3>
          <table className="small">
            <tbody>
              {BACKENDS.map((b) => {
                const v = mine.find((x) => x.backend === b);
                if (!v) return null;
                const top = Object.entries(v.probs).sort((x, y) => y[1] - x[1])[0];
                return (
                  <tr key={b}>
                    <td>{b}</td>
                    <td>{v.error ? <span className="bad">{v.error}</span> : (v.choice ?? top?.[0])}</td>
                    <td className="num">{top?.[1].toFixed(2)}</td>
                    <td className="muted">{v.rationale}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </>
      )}
      {toss && <TossTrace toss={toss} />}
      {commentary
        .filter((c) => c.moment_id === moment.moment_id)
        .map((c) => (
          <p key={c.voice} className="caption">
            <span className="muted small">{c.voice === "pbp" ? "Play-by-play" : "Colour"}:</span> {c.text}
          </p>
        ))}
    </div>
  );
}

/** Side view of the toss (ITTF Law 2.6.2, D-31): the release → apex path against the 16 cm line and a 30° cone. */
function TossTrace({ toss }: { toss: Observation }) {
  const p = toss.payload as {
    release?: { pos_m: { x: number; z?: number } };
    apex?: { pos_m: { x: number; z?: number } };
    height_m?: number;
    angle_from_vertical_rad?: number;
  };
  if (!p.release || !p.apex || p.height_m == null) return null;
  const S = 400; // px per metre
  const ox = 120;
  const oy = 150;
  const rx = 0;
  const ax = (p.apex.pos_m.x - p.release.pos_m.x) * S;
  const ay = -(p.height_m * S);
  const cone = Math.tan(Math.PI / 6) * 0.3 * S;
  const ok = p.height_m >= 0.16 && (p.angle_from_vertical_rad ?? 0) <= Math.PI / 6;
  return (
    <div className="toss">
      <h3>Serve toss</h3>
      <svg viewBox="0 0 240 170" role="img" aria-label="Side view of the serve toss">
        <line x1={ox - 100} y1={oy - 0.16 * S} x2={ox + 100} y2={oy - 0.16 * S} className="limit" />
        <text x={ox + 60} y={oy - 0.16 * S - 4} className="label">
          16 cm
        </text>
        <path d={`M${ox},${oy} L${ox - cone},${oy - 0.3 * S} L${ox + cone},${oy - 0.3 * S} Z`} className="cone" />
        <line x1={ox + rx} y1={oy} x2={ox + ax} y2={oy + ay} className={ok ? "path ok" : "path bad"} />
        <circle cx={ox + ax} cy={oy + ay} r={4} className={ok ? "ball ok" : "ball bad"} />
        <circle cx={ox} cy={oy} r={3} className="palm" />
      </svg>
      <div className="small">
        Rose {(p.height_m * 100).toFixed(1)} cm
        {p.angle_from_vertical_rad != null &&
          `, ${((p.angle_from_vertical_rad * 180) / Math.PI).toFixed(0)}° from vertical on the way up`}
        <span className="muted"> · reconstructed from tracking, not video</span>
      </div>
    </div>
  );
}

import type { Observation, TrackSample } from "@trophy/state-client";
import { TABLE_TENNIS, fitView, onField, toPx } from "../lib/world.ts";

/** The shared world state (D-21) drawn from Spacetime metadata only: no video. */
export function WorldView({
  sport,
  observations,
  trail,
}: {
  sport?: string;
  observations: Observation[];
  trail: TrackSample[];
}) {
  if (sport && sport !== "table_tennis") {
    return (
      <div className="panel">
        <h2>World state</h2>
        <p className="muted">
          The top-down view is drawn for ping pong; {sport.replace("_", " ")} events are listed below.
        </p>
        <EventList observations={observations} />
      </div>
    );
  }
  const f = TABLE_TENNIS;
  const v = fitView(f, 520);
  const [x0, y0] = toPx(f, v, -f.length / 2, f.width / 2);
  const [x1, y1] = toPx(f, v, f.length / 2, -f.width / 2);
  const [nx] = toPx(f, v, 0, 0);
  const ball = trail.filter((s) => s.object === "ball" && s.pos_m);
  const path = ball
    .map((s, i) => {
      const [x, y] = toPx(f, v, s.pos_m![0], s.pos_m![1]);
      return `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const bounces = observations.filter((o) => o.type === "bounce" && o.pos_m).slice(0, 12);
  return (
    <div className="panel">
      <h2>
        World state <span className="badge">reconstructed from tracking, not video</span>
      </h2>
      <svg
        viewBox={`0 0 ${v.w} ${v.h}`}
        className="world"
        role="img"
        aria-label="Top-down table with ball trail and bounces"
      >
        <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} className="table" />
        <line x1={x0} y1={(y0 + y1) / 2} x2={x1} y2={(y0 + y1) / 2} className="centre" />
        <line x1={nx} y1={y0 - 6} x2={nx} y2={y1 + 6} className="net" />
        <text x={x0} y={y1 + 18} className="label">
          A
        </text>
        <text x={x1 - 10} y={y1 + 18} className="label">
          B
        </text>
        {path && <path d={path} className="trail" />}
        {bounces.map((o, i) => {
          const [x, y] = toPx(f, v, o.pos_m!.x, o.pos_m!.y);
          const r = Math.max(4, (o.sigma_m ?? 0.02) * v.scale);
          const inside = onField(f, o.pos_m!.x, o.pos_m!.y);
          return (
            <g key={o.id} opacity={1 - i / 14}>
              <circle cx={x} cy={y} r={r} className={inside ? "bounce in" : "bounce out"} />
            </g>
          );
        })}
      </svg>
      <EventList observations={observations} />
    </div>
  );
}

function EventList({ observations }: { observations: Observation[] }) {
  const recent = observations.filter((o) => o.type !== "heartbeat").slice(0, 6);
  if (!recent.length) return <p className="muted small">No observations yet.</p>;
  return (
    <ul className="events small">
      {recent.map((o) => (
        <li key={o.id}>
          <span className="muted">{o.t_game_s.toFixed(1)} s</span> {o.type}
          {o.side ? ` · side ${o.side}` : ""}{" "}
          <span className="muted">
            conf {o.conf.toFixed(2)} · {o.source}
          </span>
        </li>
      ))}
    </ul>
  );
}

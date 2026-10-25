import { useState } from "react";
import type { Moment, Observation } from "@trophy/state-client";
import { FILTERS, matches, type FilterId } from "../lib/moments.ts";
import { fmtDuration } from "../lib/format.ts";

const KIND: Record<Moment["kind"], string> = {
  point: "Point",
  serve_fault: "Serve fault",
  edge: "Edge",
  challenge: "Challenge",
  basket: "Basket",
  bookmark: "Bookmark",
  house_rule: "House rule",
  rally: "Rally",
};

export function MomentsList({
  moments,
  observations,
  start,
  current,
  onPlay,
}: {
  moments: Moment[];
  observations: Observation[];
  start: number;
  current?: string;
  onPlay: (m: Moment) => void;
}) {
  const [filter, setFilter] = useState<FilterId>("all");
  const shown = moments.filter((m) => matches(m, filter, observations));
  return (
    <div className="panel">
      <h2>Moments</h2>
      <div className="chips">
        {FILTERS.map((f) => (
          <button key={f.id} className={f.id === filter ? "chip on" : "chip"} onClick={() => setFilter(f.id)}>
            {f.label}
          </button>
        ))}
      </div>
      {!moments.length && <p className="muted">No moments yet. The engine writes them live as calls happen.</p>}
      {!!moments.length && !shown.length && <p className="muted">None in this game.</p>}
      <ol className="moments">
        {shown.map((m) => (
          <li key={m.moment_id} className={m.moment_id === current ? "on" : ""}>
            <button className="moment" onClick={() => onPlay(m)}>
              <span className="t muted">{fmtDuration(m.t_game_s - start)}</span>
              <span className="kind">{m.is_best_play ? "★ Play of the game" : KIND[m.kind]}</span>
              <span className="label">{m.label}</span>
              <span className="muted small">{m.score_after}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

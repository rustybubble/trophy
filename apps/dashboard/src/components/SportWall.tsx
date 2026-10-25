// The honest sport wall: what the weekend build targets and what's only planned (mirrors rulepacks/sports.yaml).
const SPORTS: { name: string; status: "must" | "should" | "next"; calls: string }[] = [
  {
    name: "Ping pong",
    status: "must",
    calls:
      "rally scoring, edge ball, illegal serves (ITTF 2.6: toss ≥ 16 cm, near-vertical, hidden, position), net lets",
  },
  { name: "Basketball", status: "next", calls: "2 vs 3 pointers on a recorded clip (planned, not started)" },
  { name: "Pickleball", status: "next", calls: "kitchen rule, outs" },
  { name: "Tennis", status: "next", calls: "outs" },
  { name: "Badminton", status: "next", calls: "outs" },
  { name: "Volleyball", status: "next", calls: "hand over the net, outs" },
  { name: "Two-hand touch", status: "next", calls: "touches, outs, scoring" },
];

const LABEL = { must: "this weekend", should: "planned", next: "coming next · not built" };

export function SportWall() {
  return (
    <div className="panel sportwall">
      <h2>Sports</h2>
      <ul>
        {SPORTS.map((s) => (
          <li key={s.name} className={s.status}>
            <strong>{s.name}</strong> <span className={`badge ${s.status}`}>{LABEL[s.status]}</span>
            <div className="muted small">{s.calls}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

import type { GameTeam } from "@trophy/contracts";
import { fmtStat, type GameStats } from "../lib/moments.ts";
import { Table, metres, toPx } from "./Table.tsx";

const ROWS: { key: keyof GameStats["sides"][string]; label: string }[] = [
  { key: "points", label: "Points won" },
  { key: "onServe", label: "On serve" },
  { key: "onReceive", label: "On receive" },
  { key: "serveFaults", label: "Serve faults" },
  { key: "edgesFor", label: "Edge balls won" },
];

/** Stats from the game's calls and observations, labelled auto-detected; anything not detected says so. */
export function StatsPanel({ stats, teams }: { stats: GameStats; teams: GameTeam[] }) {
  return (
    <div className="panel">
      <h2>
        Stats <span className="badge">auto-detected</span>
      </h2>
      <table className="stats">
        <thead>
          <tr>
            <th />
            {teams.map((t) => (
              <th key={t.team_id} style={{ color: t.color }}>
                {t.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.key}>
              <td className="muted">{r.label}</td>
              {teams.map((t) => {
                const v = stats.sides[t.team_id]?.[r.key] ?? null;
                return (
                  <td key={t.team_id} className={v === null ? "muted small" : "num"}>
                    {fmtStat(v)}
                  </td>
                );
              })}
            </tr>
          ))}
          <tr>
            <td className="muted">Longest rally (shots)</td>
            <td colSpan={teams.length} className={stats.longestRally === null ? "muted small" : "num"}>
              {fmtStat(stats.longestRally)}
            </td>
          </tr>
        </tbody>
      </table>
      <h3>Bounce map</h3>
      {stats.bounces.length ? (
        <Table label="Where the ball bounced">
          {stats.bounces.map((b, i) => {
            const [x, y] = toPx(b.x, b.y);
            return <circle key={i} cx={x} cy={y} r={metres(0.06)} className="heat" />;
          })}
        </Table>
      ) : (
        <p className="muted small">Bounces not detected.</p>
      )}
    </div>
  );
}

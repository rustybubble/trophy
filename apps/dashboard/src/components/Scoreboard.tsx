import type { GameTeam } from "@trophy/contracts";
import type { Score } from "@trophy/state-client";

export function Scoreboard({ scores, teams, server }: { scores: Score[]; teams: GameTeam[]; server?: string }) {
  const ids = teams.length ? teams.map((t) => t.team_id) : scores.map((s) => s.team_id);
  return (
    <div className="panel scoreboard" aria-label="Score">
      {ids.map((id) => {
        const team = teams.find((t) => t.team_id === id);
        const score = scores.find((s) => s.team_id === id);
        return (
          <div key={id} className="team" style={{ borderColor: team?.color ?? "var(--line)" }}>
            <div className="name">
              {team?.name ?? `Team ${id}`}
              {server === id && (
                <span className="serve" title="Serving">
                  {" "}
                  ●
                </span>
              )}
            </div>
            <div className="points">{score?.points ?? 0}</div>
          </div>
        );
      })}
      {!ids.length && <p className="muted">No score yet.</p>}
      {scores[0]?.display && scores[0].display.includes(",") && <div className="muted">{scores[0].display}</div>}
    </div>
  );
}

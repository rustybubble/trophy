import type { Game, Score } from "@trophy/state-client";

export function Scoreboard({ game, scores, compact }: { game?: Game; scores: Score[]; compact?: boolean }) {
  const teams = game?.teams ?? [
    { team_id: "A", name: "A" },
    { team_id: "B", name: "B" },
  ];
  const pts = (id: string) => scores.find((s) => s.team_id === id)?.points ?? 0;
  return (
    <div className={compact ? "score compact" : "score"} aria-label="Score">
      {teams.map((t, i) => (
        <div key={t.team_id} className="team" style={{ borderColor: t.color ?? "transparent" }}>
          <span className="name">{t.name}</span>
          <span className="pts">{pts(t.team_id)}</span>
          {game?.server_team_id === t.team_id && <span className="serve" title="Serving" aria-label="serving" />}
          {i === 0 && <span className="sep" aria-hidden />}
        </div>
      ))}
      {!compact && game && (
        <div className="meta muted">
          {game.sport.replace("_", " ")} · {game.status}
          {game.rally_no ? ` · rally ${game.rally_no}` : ""}
        </div>
      )}
    </div>
  );
}

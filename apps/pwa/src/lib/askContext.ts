// The phone's view of the game, sent with every "ask the ref" question (interfaces-v1 §20). The referee resolves
// "that" to the newest call's time, answers the score from it, and grounds rule answers in the approved house rules,
// all without a Spacetime read of its own. Small on purpose: three calls, the scores, the rally and the server.
import type { Call, Game, HouseRule, Score } from "@trophy/state-client";

export interface AskContext {
  t_game_s: number | null;
  rally_no: number | null;
  server_team_id: string | null;
  teams: { team_id: string; name: string }[];
  scores: { team_id: string; points: number; display?: string }[];
  last_calls: Record<string, unknown>[];
  house_rules: { text: string; status: string }[];
}

const CALL_FIELDS = [
  "id",
  "kind",
  "outcome",
  "text",
  "why",
  "p",
  "tier",
  "t_game_s",
  "rally_no",
  "status",
  "rule_id",
  "team_id",
  "created_at_ms",
] as const;

export function buildAskContext(
  g: { game?: Game; scores: Score[]; calls: Call[]; houseRules: HouseRule[] },
  nowMs: number = Date.now(),
): AskContext {
  const t0 = g.game?.t0_ms;
  const live = g.calls.filter((c) => c.status !== "voided").slice(0, 3);
  return {
    t_game_s: typeof t0 === "number" ? Math.round(((nowMs - t0) / 1000) * 1000) / 1000 : null,
    rally_no: g.game?.rally_no ?? null,
    server_team_id: g.game?.server_team_id ?? null,
    teams: (g.game?.teams ?? []).map((t) => ({ team_id: t.team_id, name: t.name })),
    scores: g.scores.map((s) => ({ team_id: s.team_id, points: s.points, display: s.display })),
    last_calls: live.map((c) => {
      const out: Record<string, unknown> = {};
      for (const k of CALL_FIELDS) if (c[k] !== undefined) out[k] = c[k];
      return out;
    }),
    house_rules: g.houseRules.filter((h) => h.status === "approved").map((h) => ({ text: h.text, status: h.status })),
  };
}

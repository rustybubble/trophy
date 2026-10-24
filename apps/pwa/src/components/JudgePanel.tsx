import { useState } from "react";
import type { Api } from "../lib/api.ts";
import type { GameView } from "../lib/useGame.ts";

/** The judge's controls (interfaces-v1 §9): start, uphold/overturn, undo, score ±, house rules. */
export function JudgePanel({
  api,
  g,
  onError,
  onClose,
}: {
  api?: Api;
  g: GameView;
  onError: (m: string) => void;
  onClose: () => void;
}) {
  const [rule, setRule] = useState("");
  const send = async (cmd: string, args: Record<string, unknown> = {}) => {
    if (!api) return onError("Synthetic demo: controls are disabled");
    try {
      await api.ctl(cmd, args);
    } catch (e) {
      onError(`${cmd}: ${e instanceof Error ? e.message : String(e)}`);
    }
  };
  const open = g.challenges.find((c) => c.status === "open");
  const openCall = open ? g.calls.find((c) => c.id === open.call_id) : undefined;
  const teams = g.game?.teams ?? [];
  const rules = [...g.houseRules].sort((a, b) => b.created_at_ms - a.created_at_ms).slice(0, 3);

  return (
    <aside className="sheet judge" aria-label="Judge controls">
      <button className="ghost judge-close" aria-label="Close judge controls" onClick={onClose}>
        ×
      </button>
      <strong>Judge</strong>
      {g.game?.status === "lobby" && (
        <button className="primary" onClick={() => void send("start_game", { first_server: "A" })}>
          Start game (A serves)
        </button>
      )}
      {open && (
        <div className="challenge-open">
          <p>
            Challenge: <strong>{openCall?.text ?? open.call_id}</strong>
            {openCall?.suggested && <span className="muted"> · AI suggests {openCall.suggested} (uncalibrated)</span>}
          </p>
          <div className="row">
            <button
              className="primary"
              onClick={() => void send("resolve_challenge", { challenge_id: open.challenge_id, result: "upheld" })}
            >
              Uphold
            </button>
            <button
              onClick={() => void send("resolve_challenge", { challenge_id: open.challenge_id, result: "overturned" })}
            >
              Overturn
            </button>
          </div>
        </div>
      )}
      <div className="row">
        <button onClick={() => void send("undo_last_call")}>Undo last call</button>
        {teams.map((t) => (
          <span key={t.team_id} className="adjust">
            {t.name}
            <button
              aria-label={`${t.name} minus one`}
              onClick={() => void send("adjust_score", { team_id: t.team_id, delta: -1 })}
            >
              −
            </button>
            <button
              aria-label={`${t.name} plus one`}
              onClick={() => void send("adjust_score", { team_id: t.team_id, delta: 1 })}
            >
              +
            </button>
          </span>
        ))}
      </div>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          if (rule.trim())
            void send("submit_house_rule", { text: rule.trim(), source: "typed" }).then(() => setRule(""));
        }}
      >
        <input
          value={rule}
          maxLength={500}
          placeholder="House rule, e.g. first to 7, win by 1"
          onChange={(e) => setRule(e.target.value)}
        />
        <button type="submit">Add rule</button>
      </form>
      {rules.map((h) => (
        <div key={h.rule_version} className="rule">
          <span>
            “{h.text}” · <em>{h.status}</em>
            {h.results && ` · ${h.results.tests.filter((t) => t.pass).length}/${h.results.tests.length} tests pass`}
          </span>
          {h.status === "ready" && (
            <span className="row">
              <button
                className="primary"
                onClick={() => void send("approve_house_rule", { rule_version: h.rule_version })}
              >
                Approve
              </button>
              <button onClick={() => void send("reject_house_rule", { rule_version: h.rule_version })}>Reject</button>
            </span>
          )}
        </div>
      ))}
    </aside>
  );
}

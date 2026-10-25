import { useState } from "react";
import type { Call, Challenge } from "@trophy/state-client";
import { ctl, type Session } from "../lib/api.ts";

const TIER_TEXT = { AUTO: "AUTO", BETA: "BETA", PLAYERS: "PLAYERS DECIDE" } as const;

export function CallFeed({
  calls,
  challenges,
  session,
}: {
  calls: Call[];
  challenges: Challenge[];
  session?: Session;
}) {
  const [err, setErr] = useState<string>();
  const resolve = async (c: Challenge, result: "upheld" | "overturned") => {
    if (!session) return;
    try {
      await ctl(session, "resolve_challenge", { challenge_id: c.challenge_id, result });
      setErr(undefined);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <div className="panel">
      <h2>Calls</h2>
      {err && <p className="bad">{err}</p>}
      {!calls.length && <p className="muted">No calls yet.</p>}
      <ol className="feed">
        {calls.slice(0, 40).map((c) => {
          const open = challenges.find((x) => x.call_id === c.id && x.status === "open");
          return (
            <li key={c.id} className={`call ${c.status}`}>
              <span className={`tier ${c.tier}`}>{TIER_TEXT[c.tier]}</span>
              <div className="body">
                <div>{c.text}</div>
                <div className="muted small">
                  {c.rule_id} · {c.tier === "AUTO" ? "" : `p = ${c.p.toFixed(2)} · `}t {c.t_game_s.toFixed(1)} s ·{" "}
                  {c.status}
                  {c.rule_ref && <> · {c.rule_ref}</>}
                </div>
                {c.why && <div className="muted small">{c.why}</div>}
                {open && (
                  <div className="row">
                    <span className="warn small">Challenged</span>
                    {session && (
                      <>
                        <button onClick={() => void resolve(open, "upheld")}>Uphold</button>
                        <button onClick={() => void resolve(open, "overturned")}>Overturn</button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

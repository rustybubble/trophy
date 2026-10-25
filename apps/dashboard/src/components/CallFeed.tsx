import { useState } from "react";
import type { AiVote, Call, Camera, Challenge } from "@trophy/state-client";
import { ctl, type Session } from "../lib/api.ts";
import { ReplayModal } from "./ReplayModal.tsx";

const TIER_TEXT = { AUTO: "AUTO", BETA: "BETA", PLAYERS: "PLAYERS DECIDE" } as const;

export function CallFeed({
  calls,
  challenges,
  cameras,
  votes,
  session,
}: {
  calls: Call[];
  challenges: Challenge[];
  cameras: Camera[];
  votes: AiVote[];
  session?: Session;
}) {
  const [err, setErr] = useState<string>();
  const [replay, setReplay] = useState<string>(); // call id being replayed
  const replayCall = replay ? calls.find((c) => c.id === replay) : undefined;
  const resolve = async (c: Challenge, result: "upheld" | "overturned") => {
    if (!session) return;
    try {
      await ctl(session, "resolve_challenge", { challenge_id: c.challenge_id, result });
      setErr(undefined);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  const [labelling, setLabelling] = useState(false);
  const label = async (winner: "A" | "B") => {
    if (!session) return;
    setLabelling(true);
    try {
      // the judge's correction: everything since the previous label was ONE rally, won by `winner`. The engine
      // fixes the score now, exports the span as a labelled sample and files a correction for the Droid.
      await ctl(session, "label_rally", { winner });
      setErr(undefined);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLabelling(false);
    }
  };
  return (
    <div className="panel">
      <h2>Calls</h2>
      {session && (
        <div className="row correction">
          <span className="muted small">Judge: that was one rally, won by</span>
          <button disabled={labelling} onClick={() => void label("A")}>
            A
          </button>
          <button disabled={labelling} onClick={() => void label("B")}>
            B
          </button>
        </div>
      )}
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
                {(open || (session && c.kind !== "info")) && (
                  <div className="row actions">
                    {open && <span className="warn small">Challenged</span>}
                    {session && c.kind !== "info" && (
                      <button className="small" onClick={() => setReplay(c.id)}>
                        Replay
                      </button>
                    )}
                    {open && session && (
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
      {replayCall && session && (
        <ReplayModal
          call={replayCall}
          cameras={cameras}
          votes={votes}
          session={session}
          onClose={() => setReplay(undefined)}
        />
      )}
    </div>
  );
}

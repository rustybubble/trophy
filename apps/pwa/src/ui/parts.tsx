import { useRef, useState } from "react";
import type { Call, Feed, Game, Score } from "@trophy/state-client";
import type { AskAnswer } from "../lib/api.ts";
import type { Voice } from "../lib/voice.ts";
import { CloseIcon, MicIcon, MoreIcon } from "./icons.tsx";

export function tierLabel(c: Pick<Call, "tier" | "p">): string {
  if (c.tier === "PLAYERS") return "PLAYERS DECIDE";
  if (c.tier === "BETA") return `BETA · ${Math.round(c.p * 100)}%`;
  return "AUTO";
}

const STATUS_TAG: Partial<Record<Call["status"], string>> = {
  challenged: "under review",
  upheld: "upheld",
  overturned: "overturned",
  players_decide: "players decide",
};

/** The big call banner: what was called, who is at fault, and how sure the referee is. */
export function CallCard({ call, fresh }: { call?: Call; fresh: boolean }) {
  if (!call) {
    return (
      <div className="call empty">
        <div className="call-text" style={{ fontSize: 18 }}>
          No calls yet
        </div>
        <div className="small">Every call appears here, beeps, and is spoken with who is at fault.</div>
      </div>
    );
  }
  return (
    <div
      key={call.id}
      className={`call tier-${call.tier.toLowerCase()}${fresh ? " fresh" : ""}`}
      role="status"
      aria-live="assertive"
    >
      <div className="call-top">
        <span className="tier-badge">{tierLabel(call)}</span>
        {call.source === "annotated" && <span className="tag">annotated</span>}
        {STATUS_TAG[call.status] && <span className="tag">{STATUS_TAG[call.status]}</span>}
      </div>
      <div className="call-text">{call.text}</div>
      {call.at_fault ? (
        <div className="call-fault">
          On <b>{call.at_fault.name}</b>
        </div>
      ) : null}
    </div>
  );
}

export function TopBar(props: { game?: Game; scores: Score[]; feed?: Feed; synthetic: boolean; onMenu: () => void }) {
  const [creditOpen, setCreditOpen] = useState(false);
  const teams = props.game?.teams?.length
    ? props.game.teams
    : [
        { team_id: "A", name: "A" },
        { team_id: "B", name: "B" },
      ];
  const pts = (id: string) => props.scores.find((s) => s.team_id === id)?.points ?? 0;
  const [a, b] = [teams[0]!, teams[1] ?? { team_id: "B", name: "B" }];
  const f = props.feed;
  return (
    <header className="bar">
      <div className="bar-row">
        <div className="score" aria-label="Score">
          <span className="team">
            <span className="dot" style={{ background: a.color ?? "var(--muted)" }} />
            <span className="name">{a.name}</span>
          </span>
          <span className="pts">{pts(a.team_id)}</span>
          <span className="dash">–</span>
          <span className="pts">{pts(b.team_id)}</span>
          <span className="team b">
            <span className="name">{b.name}</span>
            <span className="dot" style={{ background: b.color ?? "var(--muted)" }} />
          </span>
        </div>
        <button className="icon-btn" aria-label="Game menu" onClick={props.onMenu}>
          <MoreIcon />
        </button>
      </div>
      {(f || props.synthetic) && (
        <div className="chips">
          {f && f.status === "playing" && (
            <span className="chip">
              <span className="pulse" /> Replayed feed
            </span>
          )}
          {f && f.status !== "playing" && <span className="chip">Replayed feed · {f.status}</span>}
          {props.synthetic && <span className="chip warn">Mock data</span>}
          {f?.source === "cc_by_online" && f.credit && (
            <button
              className={`chip credit${creditOpen ? " open" : ""}`}
              title={f.credit}
              onClick={() => setCreditOpen((o) => !o)}
            >
              {f.credit}
            </button>
          )}
        </div>
      )}
    </header>
  );
}

/**
 * Hold to talk → Cartesia Ink-2. A release during the first mic permission prompt is remembered, so the turn always
 * closes. Shows the live transcript in a bubble above the controls.
 */
export function HoldToTalk(props: {
  voice?: Voice;
  small?: boolean;
  hint: string;
  onTranscript: (t: string) => void;
  onError: (m: string) => void;
}) {
  const [state, setState] = useState<"idle" | "listening" | "thinking">("idle");
  const [partial, setPartial] = useState("");
  const holding = useRef(false);
  const pending = useRef<Promise<{ release: () => Promise<string> }> | undefined>(undefined);

  const down = (e: React.PointerEvent) => {
    e.preventDefault();
    if (!props.voice || pending.current) return;
    holding.current = true;
    setPartial("");
    setState("listening");
    pending.current = props.voice.listen(setPartial);
    pending.current.catch((err: unknown) => {
      props.onError(`Mic: ${err instanceof Error ? err.message : String(err)}`);
      pending.current = undefined;
      setState("idle");
    });
  };
  const up = async () => {
    if (!holding.current) return;
    holding.current = false;
    const p = pending.current;
    if (!p) return;
    setState("thinking");
    try {
      const text = await (await p).release();
      if (text) props.onTranscript(text);
    } catch {
      /* reported on press */
    } finally {
      pending.current = undefined;
      setState("idle");
      setTimeout(() => setPartial(""), 1500);
    }
  };
  return (
    <>
      {(state !== "idle" || partial) && !props.small && (
        <div className="bubble" aria-live="polite">
          {partial ? `“${partial}”` : state === "listening" ? "Listening…" : "…"}
          {state === "listening" && <div className="hint">{props.hint}</div>}
        </div>
      )}
      <button
        className={`mic ${state}${props.small ? " small" : ""}`}
        aria-label={props.voice ? "Hold to talk" : "Voice is unavailable"}
        title={props.voice ? props.hint : "Voice needs the referee laptop (not available in mock mode)"}
        disabled={!props.voice}
        onPointerDown={down}
        onPointerUp={() => void up()}
        onPointerCancel={() => void up()}
        onPointerLeave={() => void up()}
        onContextMenu={(e) => e.preventDefault()}
      >
        <MicIcon size={props.small ? 22 : 28} />
      </button>
    </>
  );
}

export function AnswerCard(props: { q: string; a?: AskAnswer; err?: string; onClose: () => void }) {
  return (
    <div className="answer" aria-live="polite">
      <button className="icon-btn close" aria-label="Close answer" onClick={props.onClose}>
        <CloseIcon />
      </button>
      <div className="q">“{props.q}”</div>
      {props.err ? (
        <p className="err">{props.err}</p>
      ) : props.a ? (
        <>
          <p>{props.a.answer}</p>
          {props.a.kind === "pending" && (
            <p className="small muted">The Droid is writing a check; the answer is spoken when it's ready.</p>
          )}
          {props.a.citations.length > 0 && (
            <ul className="cites">
              {props.a.citations.slice(0, 2).map((c) => (
                <li key={c.rule_id}>
                  <b>{c.rule_id}</b> {c.title}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="muted">Asking the ref…</p>
      )}
    </div>
  );
}

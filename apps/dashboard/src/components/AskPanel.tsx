import type { Ask } from "@trophy/state-client";

/** How the ref answered (Ask.kind); "" or missing on rows from older referees. */
const KIND_LABEL: Record<string, string> = {
  check: "geometry check",
  rule: "rulebook",
  score: "score",
  explain: "explained",
  pending: "pending",
  none: "no answer",
};

/** Ask-the-ref transcript (D-37): judge questions answered by a geometry check, rules questions from the rule pack. */
export function AskPanel({ asks }: { asks: Ask[] }) {
  return (
    <div className="panel">
      <h2>Ask the ref</h2>
      {!asks.length && (
        <p className="muted">Questions asked by voice on a phone show up here with their rule citations.</p>
      )}
      {asks.slice(0, 5).map((a) => (
        <div key={a.ask_id} className="ask">
          <div className="q">
            “{a.question}”{a.kind && KIND_LABEL[a.kind] && <span className="badge">{KIND_LABEL[a.kind]}</span>}
          </div>
          <div>{a.answer}</div>
          <div className="small">
            {a.check && (
              <span className="check">
                {a.check}
                {typeof a.p === "number" && <> · p {a.p.toFixed(2)}</>}
                {a.calibrated !== true && <span className="badge">uncalibrated</span>}
              </span>
            )}
            {a.citations.map((c) => (
              <a key={c.rule_id} href={c.url} target="_blank" rel="noreferrer" title={c.quote}>
                {c.rule_id} {c.title}
              </a>
            ))}
            <span className="muted"> · {a.latency_ms} ms</span>
          </div>
        </div>
      ))}
    </div>
  );
}

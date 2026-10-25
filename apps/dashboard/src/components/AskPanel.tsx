import type { Ask } from "@trophy/state-client";

/** Ask-the-ref transcript (interfaces §17): answers drawn from the official rulebooks, with citations. */
export function AskPanel({ asks }: { asks: Ask[] }) {
  return (
    <div className="panel">
      <h2>Ask the ref</h2>
      {!asks.length && (
        <p className="muted">Questions asked by voice on a phone show up here with their rule citations.</p>
      )}
      {asks.slice(0, 5).map((a) => (
        <div key={a.ask_id} className="ask">
          <div className="q">“{a.question}”</div>
          <div>{a.answer}</div>
          <div className="small">
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

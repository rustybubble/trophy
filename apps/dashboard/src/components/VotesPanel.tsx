import type { AiVote, Call } from "@trophy/state-client";

const BACKENDS: AiVote["backend"][] = ["geometry", "claude"];
const NAMES: Record<AiVote["backend"], string> = {
  geometry: "Geometry",
  claude: "Claude",
};

/** The background second opinion on close calls (D-23). The AI probabilities are uncalibrated and say so. */
export function VotesPanel({ calls, votes }: { calls: Call[]; votes: AiVote[] }) {
  const voted = calls.filter((c) => votes.some((v) => v.call_id === c.id)).slice(0, 3);
  return (
    <div className="panel">
      <h2>
        AI second opinion <span className="badge">uncalibrated</span>
      </h2>
      {!voted.length && <p className="muted">Close calls get Claude's vote here, next to the geometry.</p>}
      {voted.map((c) => (
        <div key={c.id} className="votes">
          <div className="small">
            {c.text} <span className="muted">(p = {c.p.toFixed(2)})</span>
            {c.suggested && <span className="muted"> · suggested: {c.suggested}</span>}
          </div>
          <table>
            <tbody>
              {BACKENDS.map((b) => {
                const v = votes.find((x) => x.call_id === c.id && x.backend === b);
                if (!v) return null;
                const top = Object.entries(v.probs).sort((x, y) => y[1] - x[1])[0];
                return (
                  <tr key={b}>
                    <td>{NAMES[b]}</td>
                    <td>{v.error ? <span className="bad">{v.error}</span> : (v.choice ?? top?.[0] ?? "—")}</td>
                    <td className="num">{top ? top[1].toFixed(2) : ""}</td>
                    <td className="num muted">{v.latency_ms} ms</td>
                    <td className="muted small">{v.rationale}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

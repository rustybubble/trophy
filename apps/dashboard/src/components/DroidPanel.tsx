import { useState } from "react";
import type { HouseRule } from "@trophy/state-client";
import { ctl, type Session } from "../lib/api.ts";

/** The Factory Droid house-rule compiler (interfaces §18): plan, streamed steps, diff, test table, Approve. */
export function DroidPanel({ rules, session }: { rules: HouseRule[]; session?: Session }) {
  const [err, setErr] = useState<string>();
  const decide = async (h: HouseRule, cmd: "approve_house_rule" | "reject_house_rule") => {
    if (!session) return;
    try {
      await ctl(session, cmd, { rule_version: h.rule_version });
      setErr(undefined);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  const h = rules[0];
  return (
    <div className="panel">
      <h2>House rules · Factory Droid</h2>
      {err && <p className="bad">{err}</p>}
      {!h && <p className="muted">Say or type a house rule on a judge phone; the Droid compiles and tests it here.</p>}
      {h && (
        <div className="droid">
          <div>
            “{h.text}” <span className={`status ${h.status}`}>{h.status}</span>
            <span className="muted small"> · {h.backend === "droid" ? "Factory Droid" : "Claude fallback"}</span>
          </div>
          {h.plan_md && <pre className="plan">{h.plan_md}</pre>}
          {!!h.steps.length && (
            <ol className="steps small">
              {h.steps.slice(-8).map((s, i) => (
                <li key={i} className={s.kind}>
                  <span className="muted">{s.kind}</span> {s.text}
                </li>
              ))}
            </ol>
          )}
          {h.diff && <pre className="diff">{h.diff}</pre>}
          {h.results && (
            <>
              <table className="small">
                <tbody>
                  {h.results.tests.map((t) => (
                    <tr key={t.name}>
                      <td className={t.pass ? "ok" : "bad"}>{t.pass ? "pass" : "fail"}</td>
                      <td>{t.name}</td>
                      <td className="muted">
                        {t.before ?? ""} {t.after ? `→ ${t.after}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!!h.results.calls_changed.length && (
                <p className="small">
                  Calls that would change:{" "}
                  {h.results.calls_changed.map((c) => `rally ${c.rally_no} (${c.before} → ${c.after})`).join(", ")}
                </p>
              )}
            </>
          )}
          {h.error && <p className="bad small">{h.error}</p>}
          {h.status === "ready" && session && (
            <div className="row">
              <button className="primary" onClick={() => void decide(h, "approve_house_rule")}>
                Approve
              </button>
              <button onClick={() => void decide(h, "reject_house_rule")}>Reject</button>
            </div>
          )}
        </div>
      )}
      {rules.length > 1 && (
        <p className="muted small">
          Earlier:{" "}
          {rules
            .slice(1, 4)
            .map((r) => `“${r.text}” (${r.status})`)
            .join(" · ")}
        </p>
      )}
    </div>
  );
}

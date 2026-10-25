import { useState } from "react";
import type { DroidRun, HouseRule } from "@trophy/state-client";
import { ctl, type Session } from "../lib/api.ts";

type Cmd = (cmd: string, args?: Record<string, unknown>) => Promise<void>;

/**
 * The Factory Droid's work, every run of every kind (D-43): what triggered it, its plan, live steps, the diff, the
 * test table, the calls it changed in this game, blocked tool calls, timings, and for a house rule the Droid's
 * decision with a one-tap Undo. House rules from a compiler that writes no droid_run row still show (fallback).
 */
export function DroidPanel({ runs, rules, session }: { runs: DroidRun[]; rules: HouseRule[]; session?: Session }) {
  const [err, setErr] = useState<string>();
  const send: Cmd = async (cmd, args = {}) => {
    if (!session) return;
    try {
      await ctl(session, cmd, args);
      setErr(undefined);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  const byVersion = new Map(rules.map((h) => [h.rule_version, h]));
  const linked = new Set(runs.map((r) => r.trigger.rule_version).filter(Boolean));
  const orphans = rules.filter((h) => !linked.has(h.rule_version));
  return (
    <div className="panel">
      <h2>Factory Droid</h2>
      {err && <p className="bad">{err}</p>}
      {session && (
        <div className="row">
          <button onClick={() => void send("regenerate_interpreter", { reason: "Regenerate interpreter (dashboard)" })}>
            Regenerate interpreter
          </button>
        </div>
      )}
      {!runs.length && !orphans.length && (
        <p className="muted">
          Say or type a house rule on a judge phone: the Droid writes it, tests it on this game and decides. A sport
          with no interpreter gets one written when its game starts.
        </p>
      )}
      {runs.map((r, i) => (
        <Run
          key={r.run_id}
          run={r}
          rule={r.trigger.rule_version ? byVersion.get(r.trigger.rule_version) : undefined}
          open={i === 0}
          onCmd={session ? send : undefined}
        />
      ))}
      {orphans.slice(0, 3).map((h) => (
        <RuleOnly key={h.rule_version} rule={h} onCmd={session ? send : undefined} />
      ))}
    </div>
  );
}

const KIND: Record<DroidRun["kind"], string> = {
  interpreter: "Interpreter",
  house_rule: "House rule",
  new_check: "New check",
  calibrate_checks: "Calibration",
  compile: "New sport",
  retune: "Retune",
};

function trigger(r: DroidRun): string {
  const t = r.trigger;
  switch (t.source) {
    case "sport_module":
      return `Event: a ${r.sport.replace("_", " ")} game started with no approved interpreter`;
    case "user":
      return "Judge: Regenerate interpreter";
    case "house_rule":
      return `House rule: “${t.text ?? ""}”`;
    case "session":
      return `Session: ${t.text ?? "a question no check answers"}`;
    case "health_stat":
      return `Health alarm: ${t.metric ?? ""} ${t.value ?? ""}`;
    default:
      return `CLI${t.text ? `: ${t.text}` : ""}`;
  }
}

const secs = (ms?: number | null) => (ms == null ? "" : `${(ms / 1000).toFixed(1)} s`);

function Run({ run: r, rule, open, onCmd }: { run: DroidRun; rule?: HouseRule; open: boolean; onCmd?: Cmd }) {
  const status = rule && ["applied", "reverted", "rejected"].includes(rule.status) ? rule.status : r.status;
  const tests = r.results?.tests ?? [];
  const passed = tests.filter((t) => t.pass).length;
  const applied = rule?.status === "applied" || rule?.status === "reverted";
  const changes = (applied ? rule?.results?.calls_changed : undefined) ?? r.results?.calls_changed ?? [];
  return (
    <details className="droid" open={open}>
      <summary>
        <strong>{KIND[r.kind]}</strong> · {r.sport.replace("_", " ")}{" "}
        <span className={`status ${status}`}>{status}</span>
        <span className="muted small">
          {" "}
          · attempt {r.attempt}/{r.max_attempts}
          {r.duration_ms != null ? ` · ${secs(r.duration_ms)}` : ""}
          {r.gate_ms?.length ? ` · gate ${r.gate_ms.map((g) => `${g} ms`).join(", ")}` : ""}
          {r.token_usage ? ` · ${(r.token_usage.input ?? 0) + (r.token_usage.output ?? 0)} tokens` : ""}
        </span>
      </summary>
      <p className="small">{trigger(r)}</p>
      <Decision run={r} rule={rule} />
      {rule && onCmd && <RuleActions rule={rule} onCmd={onCmd} />}
      {r.plan_md && <pre className="plan">{r.plan_md}</pre>}
      {!!r.steps.length && (
        <ol className="steps small">
          {r.steps.slice(-10).map((s, i) => (
            <li key={i} className={s.kind}>
              <span className="muted">
                {secs(s.t_ms)} {s.kind}
              </span>{" "}
              {s.text}
            </li>
          ))}
        </ol>
      )}
      {!!r.blocked?.length && (
        <p className="small bad">
          Blocked by the sandbox ({r.blocked.length}): {r.blocked.slice(-3).join(" · ")}
        </p>
      )}
      {r.diff && (
        <details>
          <summary className="small">Diff</summary>
          <pre className="diff">{r.diff}</pre>
        </details>
      )}
      {!!tests.length && (
        <details open={open && !r.results?.passed}>
          <summary className="small">
            Tests: {passed}/{tests.length} passed{r.results?.passed ? " ✓" : ""}
          </summary>
          <table className="small">
            <tbody>
              {tests.map((t) => (
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
        </details>
      )}
      {!!changes.length && (
        <div className="small">
          {rule?.status === "applied" ? "Calls changed in this game:" : "Calls that change:"}
          <ul>
            {changes.slice(0, 8).map((c, i) => (
              <li key={i}>
                rally {c.rally_no}: {c.before} → <strong>{c.after}</strong>
              </li>
            ))}
          </ul>
        </div>
      )}
      {r.error && <p className="bad small">{r.error}</p>}
    </details>
  );
}

function Decision({ run, rule }: { run: DroidRun; rule?: HouseRule }) {
  const d = rule?.decision;
  if (d) {
    const by = d.decided_by === "droid" ? "The Droid" : "The judge";
    return (
      <p className="small">
        <strong>{d.applies ? `${by} applied it` : `${by} did not apply it`}</strong>
        {d.applies && d.calls_changed != null
          ? ` · ${d.calls_changed} call(s) changed, ${d.rejudged_rallies ?? 0} plays re-judged`
          : ""}
        {rule?.status === "reverted" ? " · undone" : ""}
        {d.rationale ? ` — ${d.rationale}` : ""}
      </p>
    );
  }
  if (run.decision) {
    return (
      <p className="small">
        <strong>Droid's decision: {run.decision.applies ? "applies" : "does not apply"}</strong> —{" "}
        {run.decision.rationale}
      </p>
    );
  }
  return null;
}

function RuleActions({ rule, onCmd }: { rule: HouseRule; onCmd: Cmd }) {
  const v = { rule_version: rule.rule_version };
  if (rule.status === "applied")
    return (
      <div className="row">
        <button className="primary" onClick={() => void onCmd("revert_house_rule", v)}>
          Undo house rule
        </button>
      </div>
    );
  if (["pending", "compiling", "ready"].includes(rule.status))
    return (
      <div className="row">
        {rule.status === "ready" && !rule.decision && (
          <button className="primary" onClick={() => void onCmd("approve_house_rule", v)}>
            Approve
          </button>
        )}
        <button onClick={() => void onCmd("reject_house_rule", v)}>Veto</button>
      </div>
    );
  return null;
}

/** A house rule whose run wrote no droid_run row (an older compiler): the row itself. */
function RuleOnly({ rule: h, onCmd }: { rule: HouseRule; onCmd?: Cmd }) {
  return (
    <details className="droid">
      <summary>
        <strong>House rule</strong> “{h.text}” <span className={`status ${h.status}`}>{h.status}</span>
      </summary>
      {h.plan_md && <pre className="plan">{h.plan_md}</pre>}
      {h.diff && <pre className="diff">{h.diff}</pre>}
      {h.error && <p className="bad small">{h.error}</p>}
      {onCmd && <RuleActions rule={h} onCmd={onCmd} />}
    </details>
  );
}

import { useState } from "react";
import type { DroidRun, HouseRule } from "@trophy/state-client";
import { diffLineKind, mdToText } from "../lib/demo.ts";
import type { Voice } from "../lib/voice.ts";
import { HoldToTalk } from "./parts.tsx";
import { Sheet } from "./Sheet.tsx";

/** One card per house rule (with its Droid run) or per run of another kind (interpreter, new check, …). */
export interface DroidItem {
  key: string;
  rule?: HouseRule;
  run?: DroidRun;
  at: number;
}

export function droidItems(rules: HouseRule[], runs: DroidRun[]): DroidItem[] {
  const items: DroidItem[] = rules.map((r) => ({
    key: r.rule_version,
    rule: r,
    run: runs.find((x) => x.trigger.rule_version === r.rule_version),
    at: r.created_at_ms,
  }));
  for (const run of runs) {
    if (run.trigger.rule_version && rules.some((r) => r.rule_version === run.trigger.rule_version)) continue;
    items.push({ key: run.run_id, run, at: run.started_at_ms });
  }
  return items.sort((a, b) => b.at - a.at);
}

const STAGES = ["Received", "Writing", "Testing", "Decided", "Applied"];

function stageOf(item: DroidItem): { reached: number; stop?: string; live: boolean } {
  const r = item.rule;
  const run = item.run;
  const steps = run?.steps ?? r?.steps ?? [];
  const testing = steps.some((s) => s.kind === "test");
  if (r) {
    switch (r.status) {
      case "pending":
        return { reached: 0, live: true };
      case "compiling":
        return { reached: testing ? 2 : 1, live: true };
      case "ready":
        return { reached: 3, live: !r.decision };
      case "approved":
      case "applied":
        return { reached: 4, live: false };
      case "failed":
        return { reached: testing ? 2 : 1, stop: "Failed", live: false };
      case "rejected":
        return { reached: 3, stop: "Rejected", live: false };
      case "reverted":
        return { reached: 4, stop: "Undone", live: false };
    }
  }
  switch (run?.status) {
    case "queued":
      return { reached: 0, live: true };
    case "running":
      return { reached: testing ? 2 : 1, live: true };
    case "ready":
      return { reached: 3, live: false };
    case "approved":
      return { reached: 4, live: false };
    case "rejected":
      return { reached: 3, stop: "Rejected", live: false };
    default:
      return { reached: testing ? 2 : 1, stop: "Failed", live: false };
  }
}

const KIND_LABEL: Record<DroidRun["kind"], string> = {
  house_rule: "House rule",
  interpreter: "Interpreter",
  new_check: "New check",
  calibrate_checks: "Calibrate checks",
  compile: "Sport module",
  retune: "Retune",
};

function triggerText(item: DroidItem): string {
  if (item.rule) return `${item.rule.source === "voice" ? "Spoken" : "Typed"} house rule`;
  const t = item.run!.trigger;
  const src = { cli: "Command line", house_rule: "House rule", session: "Session event", health_stat: "Health stat" }[
    t.source
  ];
  return `${src}${t.text ? `: ${t.text}` : ""}`;
}

const clock = (ms: number) =>
  new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

function RunCard(props: {
  item: DroidItem;
  open: boolean;
  onToggle: () => void;
  onAct: (cmd: "revert_house_rule" | "reject_house_rule", ruleVersion: string) => void;
}) {
  const { item, open } = props;
  const { rule, run } = item;
  const title = rule ? `“${rule.text}”` : `${KIND_LABEL[run!.kind]} · ${run!.sport.replace(/_/g, " ")}`;
  const status = rule?.status ?? run!.status;
  const stage = stageOf(item);
  const plan = mdToText(run?.plan_md || rule?.plan_md || "");
  const steps = run?.steps ?? rule?.steps ?? [];
  const diff = run?.diff || rule?.diff || "";
  const tests = run?.results?.tests ?? rule?.results?.tests ?? [];
  const changed = run?.results?.calls_changed ?? rule?.results?.calls_changed ?? [];
  const blocked = run?.blocked ?? [];
  const decision = rule?.decision;
  const error = rule?.error ?? run?.error;

  return (
    <article className="run">
      <button className="run-head" onClick={props.onToggle} aria-expanded={open}>
        <span className="t">
          <b>{title}</b>
          <span className="small muted">
            {triggerText(item)} · {clock(item.at)}
            {rule && run ? ` · ${KIND_LABEL[run.kind]}` : ""}
          </span>
        </span>
        <span className={`status-pill ${status}`}>{status === "reverted" ? "undone" : status}</span>
      </button>

      <div className="timeline" aria-label="Progress">
        {STAGES.map((s, i) => {
          const isStop = stage.stop && i === stage.reached;
          const cls = isStop
            ? "stop"
            : i < stage.reached || (i === stage.reached && !stage.live)
              ? "done"
              : i === stage.reached
                ? "now"
                : "";
          return (
            <div key={s} className={cls}>
              <i />
              {isStop ? stage.stop : i === 4 && !rule && run?.kind !== "house_rule" ? "Approved" : s}
            </div>
          );
        })}
      </div>

      {decision && (
        <div className={`decision${decision.applies ? "" : " no"}`}>
          <b>
            {decision.decided_by === "judge" ? "Judge" : "Droid"} decided: {decision.applies ? "apply" : "don't apply"}
          </b>
          <span>{decision.rationale}</span>
          {(decision.rejudged_rallies !== undefined || decision.calls_changed !== undefined) && (
            <span className="small muted">
              Re-judged {decision.rejudged_rallies ?? 0} rallies · {decision.calls_changed ?? changed.length} call
              {(decision.calls_changed ?? changed.length) === 1 ? "" : "s"} changed
            </span>
          )}
        </div>
      )}
      {error && <div className="small err">{error}</div>}

      {rule && (status === "applied" || status === "ready") && (
        <div className="run-actions">
          {status === "applied" && (
            <button className="btn" onClick={() => props.onAct("revert_house_rule", rule.rule_version)}>
              Undo
            </button>
          )}
          {status === "ready" && (
            <button className="btn danger" onClick={() => props.onAct("reject_house_rule", rule.rule_version)}>
              Reject
            </button>
          )}
        </div>
      )}

      {open && (
        <>
          {plan && (
            <div className="sub">
              <h4>Plan</h4>
              <p className="plan">{plan}</p>
            </div>
          )}
          {steps.length > 0 && (
            <div className="sub">
              <h4>Steps{stage.live ? " · live" : ""}</h4>
              <ol className="steps">
                {steps.map((s, i) => (
                  <li key={i}>
                    <span className="muted mono small">{(s.t_ms / 1000).toFixed(1)}s</span>
                    <span className={`k ${s.kind}`}>{s.kind}</span>
                    <span>{s.text}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {diff && (
            <div className="sub">
              <h4>Diff</h4>
              <pre className="diff mono">
                {diff.split("\n").map((l, i) => (
                  <div key={i} className={diffLineKind(l)}>
                    {l || " "}
                  </div>
                ))}
              </pre>
            </div>
          )}
          {tests.length > 0 && (
            <div className="sub">
              <h4>
                Tests · {tests.filter((t) => t.pass).length}/{tests.length} pass
              </h4>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Test</th>
                    <th>Before</th>
                    <th>After</th>
                    <th className="num" />
                  </tr>
                </thead>
                <tbody>
                  {tests.map((t) => (
                    <tr key={t.name}>
                      <td>{t.name}</td>
                      <td className="muted">{t.before || "—"}</td>
                      <td>{t.after || "—"}</td>
                      <td className={`num ${t.pass ? "pass" : "fail"}`}>{t.pass ? "✓" : "✗"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {(rule || run?.kind === "house_rule") && (
            <div className="sub">
              <h4>Calls changed · {changed.length}</h4>
              {changed.length ? (
                <ul className="steps">
                  {changed.map((c, i) => (
                    <li key={i} style={{ gridTemplateColumns: "60px 1fr" }}>
                      <span className="muted small">rally {c.rally_no}</span>
                      <span>
                        <s className="muted">{c.before}</s> → <b>{c.after}</b>
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="small muted">None {stage.reached >= 3 ? "" : "yet"}</span>
              )}
            </div>
          )}
          {blocked.length > 0 && (
            <div className="sub">
              <h4>Blocked by the guard · {blocked.length}</h4>
              <ul className="steps">
                {blocked.map((b, i) => (
                  <li key={i} style={{ gridTemplateColumns: "1fr" }}>
                    <span className="mono small">{b}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {run && (
            <div className="small muted">
              {run.backend === "droid" ? "Factory Droid" : "Claude fallback"} · {run.model} · attempt {run.attempt}/
              {run.max_attempts}
              {run.duration_ms ? ` · ${(run.duration_ms / 1000).toFixed(1)} s` : ""}
              {run.gate_ms?.length ? ` · gate ${run.gate_ms.map((g) => `${(g / 1000).toFixed(1)} s`).join(", ")}` : ""}
            </div>
          )}
        </>
      )}
      <button className="more" onClick={props.onToggle}>
        {open ? "Hide the work" : "Show the work: plan, steps, diff, tests"}
      </button>
    </article>
  );
}

/** The Factory Droid's work, visible (D-43): house rules in, the Droid writes, tests and decides them. */
export function DroidSheet(props: {
  rules: HouseRule[];
  runs: DroidRun[];
  voice?: Voice;
  onSubmit: (text: string, source: "typed" | "voice") => Promise<boolean>;
  onAct: (cmd: "revert_house_rule" | "reject_house_rule", ruleVersion: string) => void;
  onError: (m: string) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const items = droidItems(props.rules, props.runs);
  const [openKey, setOpenKey] = useState<string | undefined>(() => items[0]?.key);
  const newest = items[0]?.key;
  const [lastNewest, setLastNewest] = useState(newest);
  if (newest !== lastNewest) {
    // a new run arrived: show its work as it happens
    setLastNewest(newest);
    setOpenKey(newest);
  }

  const submit = async (t: string, source: "typed" | "voice") => {
    if (!t.trim()) return;
    setBusy(true);
    if (await props.onSubmit(t.trim(), source)) setText("");
    setBusy(false);
  };

  return (
    <Sheet title="Droid" onClose={props.onClose} tall>
      <section className="section">
        <h3>New house rule</h3>
        <form
          className="rule-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(text, "typed");
          }}
        >
          <input
            className="textin"
            value={text}
            maxLength={500}
            placeholder="e.g. first to 7, win by 1"
            onChange={(e) => setText(e.target.value)}
            enterKeyHint="send"
          />
          <HoldToTalk
            voice={props.voice}
            small
            hint="Say the rule"
            onTranscript={(t) => void submit(t.replace(/^(house rule|new rule)[:,]?\s*/i, ""), "voice")}
            onError={props.onError}
          />
          <button className="btn primary" type="submit" disabled={busy || !text.trim()}>
            Send
          </button>
        </form>
        {!text && (
          <div className="suggest">
            {["First to 7, win by 1", "Serves that clip the net are replayed"].map((s) => (
              <button key={s} className="pill" onClick={() => setText(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        <p className="fine">
          The Droid writes the rule in a sandbox, tests it against this session's plays, and decides whether it applies.
          You can undo it in one tap.
        </p>
      </section>

      <section className="section">
        <h3>Runs</h3>
        {items.length ? (
          items.map((it) => (
            <RunCard
              key={it.key}
              item={it}
              open={openKey === it.key}
              onToggle={() => setOpenKey((k) => (k === it.key ? undefined : it.key))}
              onAct={props.onAct}
            />
          ))
        ) : (
          <p className="small muted">No Droid runs yet.</p>
        )}
      </section>
    </Sheet>
  );
}

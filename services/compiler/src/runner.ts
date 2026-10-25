/**
 * The compile loop: sandbox -> draft -> gate (replay_test | check_test) -> repair (at most max_attempts) -> ready | failed.
 *
 * The runner, not the agent, is the source of truth: it computes the diff from git, runs the gate itself, audits
 * every changed path against the allowlist after the turn, and enforces the wall-clock timeout. Each change to the
 * run row goes to the sink immediately so a dashboard can render it live.
 */
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type { DroidRun, DroidRunDecision, DroidRunStep } from "@trophy/contracts";

import type { Agent, AgentEvent, AgentFactory } from "./agent.ts";
import { DECISION_FILE } from "./allowlist.ts";
import type { CompilerConfig } from "./config.ts";
import { formatTestTable, runGate } from "./gate.ts";
import { changedFiles, commitSandbox, createSandbox, type Job, sandboxDiff } from "./sandbox.ts";
import type { RunSink } from "./sink.ts";

export interface RunDeps {
  config: CompilerConfig;
  agentFactory: AgentFactory;
  sink: RunSink;
  runId?: string;
  now?: () => number;
}

const ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

export function newRunId(now = Date.now()): string {
  let t = now;
  let time = "";
  for (let i = 0; i < 10; i++) {
    time = ULID_ALPHABET[t % 32] + time;
    t = Math.floor(t / 32);
  }
  const r = randomBytes(16);
  let rand = "";
  for (let i = 0; i < 16; i++) rand += ULID_ALPHABET[r[i]! % 32];
  return time + rand;
}

function triggerOf(job: Job): DroidRun["trigger"] {
  if (job.kind === "new_check") {
    // a question asked during the session; the evidence is the session's own track
    return { source: "session", text: job.newCheck?.question, samples: [job.newCheck?.sessionTrack ?? ""] };
  }
  if (job.kind === "interpreter") {
    // an event (a game started for a sport with no interpreter), a judge's "Regenerate", or the CLI
    const source = job.triggerSource ?? "cli";
    return {
      source,
      text: job.text ?? `write the ${job.sport} let/out/fault interpreter`,
      samples: [job.fixturesDir ?? `evals/fixtures/annotated/${job.sport}`],
      ...(source === "cli" ? {} : { requested_by: "engine" }),
    };
  }
  if (job.kind === "calibrate_checks") {
    // a calibration belongs to a session (D-36); the field and samples it was built from are the evidence
    return {
      source: "session",
      text: job.text,
      samples: [job.fieldPath ?? join(job.samplesDir, "field.json"), job.samplesDir],
    };
  }
  return {
    source: job.ruleVersion ? "house_rule" : "cli",
    rule_version: job.ruleVersion,
    text: job.text,
    scene: job.scene,
    ...(job.session ? { samples: [job.session] } : {}),
  };
}

/** house_rule: the Droid's decision.json, validated. */
export function readDecision(dir: string): { decision?: DroidRunDecision; error?: string } {
  const p = join(dir, DECISION_FILE);
  if (!existsSync(p)) return { error: `${DECISION_FILE} is missing` };
  let o: unknown;
  try {
    o = JSON.parse(readFileSync(p, "utf8"));
  } catch (e) {
    return { error: `${DECISION_FILE} is not JSON: ${(e as Error).message}` };
  }
  const d = o as Partial<DroidRunDecision> | null;
  if (!d || typeof d !== "object" || typeof d.applies !== "boolean")
    return { error: `${DECISION_FILE}: "applies" must be true or false` };
  if (typeof d.rationale !== "string" || !d.rationale.trim())
    return { error: `${DECISION_FILE}: "rationale" must be a non-empty string` };
  return { decision: { applies: d.applies, rationale: d.rationale.trim().slice(0, 600) } };
}

export async function runJob(job: Job, deps: RunDeps): Promise<DroidRun> {
  const now = deps.now ?? Date.now;
  const t0 = now();
  const runId = deps.runId ?? job.runId ?? newRunId(t0);
  const workspace = join(deps.config.runsDir, runId, "workspace");
  mkdirSync(join(deps.config.runsDir, runId), { recursive: true });

  const run: DroidRun = {
    schema: "trophy.droid_run.v1",
    run_id: runId,
    game_id: job.gameId ?? null,
    sport: job.sport,
    base_sport: job.kind === "compile" ? (job.baseSport ?? "table_tennis") : null,
    kind: job.kind,
    trigger: triggerOf(job),
    status: "queued",
    backend: "droid",
    model: deps.config.model,
    attempt: 0,
    max_attempts: deps.config.maxAttempts,
    plan_md: "",
    steps: [],
    diff: "",
    results: null,
    allowlist: [],
    blocked: [],
    workspace,
    commit: null,
    module_version: null,
    error: null,
    started_at_ms: t0,
    updated_at_ms: t0,
    finished_at_ms: null,
    duration_ms: null,
    gate_ms: [],
    token_usage: null,
    ...(job.kind === "house_rule" ? { decision: null } : {}),
  };
  const emit = async () => {
    run.updated_at_ms = now();
    await deps.sink.update(structuredClone(run));
  };
  const step = (e: AgentEvent): DroidRunStep => {
    const s: DroidRunStep = { t_ms: now() - t0, attempt: run.attempt, ...e };
    run.steps.push(s);
    if (e.kind === "blocked") run.blocked!.push(e.text);
    return s;
  };
  const finish = async (status: "ready" | "failed", error?: string) => {
    run.status = status;
    run.error = error ?? null;
    run.finished_at_ms = now();
    run.duration_ms = run.finished_at_ms - t0;
    if (error) step({ kind: "error", text: error });
    await emit();
    return run;
  };

  await emit();
  let sb;
  try {
    sb = createSandbox(job, workspace, deps.config.enginePython);
  } catch (e) {
    return finish("failed", `sandbox: ${(e as Error).message}`);
  }
  run.allowlist = sb.allowlist;
  run.status = "running";
  step({ kind: "message", text: `sandbox ready at ${workspace}; allowlist: ${sb.allowlist.join(", ")}` });
  await emit();

  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(new Error(`timeout after ${deps.config.timeoutMs / 1000} s`)),
    deps.config.timeoutMs,
  );
  let agent: Agent | undefined;
  try {
    agent = await deps.agentFactory({
      sandboxDir: sb.dir,
      allowlist: sb.allowlist,
      gate: sb.gate,
      model: deps.config.model,
      reasoningEffort: deps.config.reasoningEffort,
    });
    // The brief goes in the first prompt (it is also TASK.md in the sandbox) so the agent needs no exploratory turn.
    const gateCmd = `./${sb.gate}`;
    let prompt = `${readFileSync(join(sb.dir, "TASK.md"), "utf8")}\n\nBegin now: plan in 3-5 lines, then edit, then run ${gateCmd}.`;
    let lastTable = "";
    let repairWhy = "";
    for (let attempt = 1; attempt <= deps.config.maxAttempts; attempt++) {
      run.attempt = attempt;
      if (attempt > 1) {
        step({ kind: "repair", text: `attempt ${attempt}: ${repairWhy || "repairing after failed checks"}` });
        prompt = repairWhy
          ? `${repairWhy} Only edit: ${sb.allowlist.join(", ")}. Then run ${gateCmd}.\n\n${lastTable}`
          : `${gateCmd} failed. Fix the ${sb.gate === "check_test" ? "checks" : "module"} and run ${gateCmd} again. Only edit: ${sb.allowlist.join(", ")}.\n\n${lastTable}`;
        repairWhy = "";
      }
      await emit();
      let firstMessage = attempt === 1;
      const result = await agent.turn(
        prompt,
        (e) => {
          const s = step(e);
          if (firstMessage && e.kind === "message") {
            firstMessage = false;
            run.plan_md = e.text;
            s.kind = "plan";
          }
          void emit();
        },
        controller.signal,
      );
      if (result.tokenUsage) {
        const tu = run.token_usage ?? { input: 0, output: 0 };
        run.token_usage = {
          input: (tu.input ?? 0) + result.tokenUsage.input,
          output: (tu.output ?? 0) + result.tokenUsage.output,
        };
      }
      if (controller.signal.aborted) break;
      if (!result.success) {
        step({ kind: "error", text: `agent turn failed: ${result.error ?? "unknown"}` });
      }
      run.diff = sandboxDiff(sb);
      const touched = changedFiles(sb);
      const outside = touched.filter((p) => !sb.allowlist.includes(p));
      if (outside.length) {
        clearTimeout(timer);
        return finish("failed", `allowlist violation: the agent changed ${outside.join(", ")}`);
      }
      if (!touched.length) {
        // A gate that passes on an unchanged module proves nothing: the job asked for a change.
        step({ kind: "error", text: `attempt ${attempt}: the agent changed nothing in ${sb.allowlist.join(", ")}` });
        lastTable = `You did not change any file. The job requires editing ${sb.allowlist.join(", ")}; use the Edit or Create tool directly.`;
        await emit();
        if (!result.success) break;
        continue;
      }
      if (job.kind === "house_rule") {
        // D-43: the Droid decides whether the rule applies; the engine acts on it only with a passing gate
        const { decision, error } = readDecision(sb.dir);
        const rulesFile = `sports/${job.sport}/rules.yaml`;
        const why = error
          ? `${error}. Write ${DECISION_FILE} as {"applies": true|false, "rationale": "<one or two sentences>"}.`
          : decision!.applies && !touched.includes(rulesFile)
            ? `${DECISION_FILE} says the rule applies, but ${rulesFile} is unchanged: implement the rule, or decide it does not apply.`
            : "";
        run.decision = decision ?? null;
        if (why) {
          step({ kind: "error", text: `attempt ${attempt}: ${why}` });
          repairWhy = why;
          await emit();
          if (!result.success) break;
          continue;
        }
        step({
          kind: "message",
          text: `decision: ${decision!.applies ? "applies" : "does not apply"}: ${decision!.rationale}`,
        });
      }
      step({ kind: "test", text: `runner: ${gateCmd} (attempt ${attempt})` });
      await emit();
      let gate;
      try {
        gate = await runGate(sb.dir, sb.gate);
      } catch (e) {
        clearTimeout(timer);
        return finish("failed", `gate: ${(e as Error).message}`);
      }
      run.gate_ms!.push(gate.ms);
      run.results = gate.results;
      lastTable = formatTestTable(gate.results);
      step({ kind: "test", text: `${gate.results.summary} (${gate.ms} ms)` });
      await emit();
      if (gate.results.passed) {
        const what =
          job.text ??
          (job.kind === "calibrate_checks"
            ? "calibrated checks"
            : job.kind === "interpreter"
              ? "interpreter"
              : "derived module");
        run.commit = commitSandbox(sb, `${job.kind} ${job.sport}: ${what} (run ${runId})`);
        clearTimeout(timer);
        return finish("ready");
      }
      if (!result.success && !touched.length) break; // the agent did nothing and reported failure: repairing won't help
    }
    clearTimeout(timer);
    if (controller.signal.aborted) {
      return finish("failed", String((controller.signal.reason as Error)?.message ?? "aborted"));
    }
    return finish("failed", `checks still failing after ${run.attempt} attempt(s)`);
  } catch (e) {
    clearTimeout(timer);
    const reason = controller.signal.aborted
      ? String((controller.signal.reason as Error)?.message ?? "aborted")
      : (e as Error).message;
    return finish("failed", reason);
  } finally {
    await agent?.close().catch(() => undefined);
  }
}

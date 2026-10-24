/**
 * The compile loop: sandbox -> draft -> replay_test -> repair (at most max_attempts) -> ready | failed.
 *
 * The runner, not the agent, is the source of truth: it computes the diff from git, runs the gate itself, audits
 * every changed path against the allowlist after the turn, and enforces the wall-clock timeout. Each change to the
 * run row goes to the sink immediately so a dashboard can render it live.
 */
import { randomBytes } from "node:crypto";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

import type { DroidRun, DroidRunStep } from "@trophy/contracts";

import type { Agent, AgentEvent, AgentFactory } from "./agent.ts";
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
  return {
    source: job.ruleVersion ? "house_rule" : "cli",
    rule_version: job.ruleVersion,
    text: job.text,
    scene: job.scene,
  };
}

export async function runJob(job: Job, deps: RunDeps): Promise<DroidRun> {
  const now = deps.now ?? Date.now;
  const t0 = now();
  const runId = deps.runId ?? newRunId(t0);
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
    agent = await deps.agentFactory({ sandboxDir: sb.dir, allowlist: sb.allowlist, model: deps.config.model });
    let prompt = "Read TASK.md and carry it out. Start with your plan.";
    let lastTable = "";
    for (let attempt = 1; attempt <= deps.config.maxAttempts; attempt++) {
      run.attempt = attempt;
      if (attempt > 1) {
        step({ kind: "repair", text: `attempt ${attempt}: repairing after failed checks` });
        prompt = `./replay_test failed. Fix the module and run ./replay_test again. Only edit: ${sb.allowlist.join(", ")}.\n\n${lastTable}`;
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
      step({ kind: "test", text: `runner: ./replay_test (attempt ${attempt})` });
      await emit();
      let gate;
      try {
        gate = await runGate(sb.dir);
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
        run.commit = commitSandbox(sb, `${job.kind} ${job.sport}: ${job.text ?? "derived module"} (run ${runId})`);
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

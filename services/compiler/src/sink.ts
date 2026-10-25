/**
 * Where a run's live state goes. `DroidRun` (droidrun.schema.json) is the row the dashboard renders; every sink gets
 * the full row on each change. JSONL keeps the history on disk. Spacetime gets every run of every kind as a droid_run
 * row (update_droid_run: trigger, plan, steps, diff, results, blocked calls, attempts, timings, tokens, decision) and,
 * for house rules, the house_rule row's progress too (update_house_rule_progress), which is what the engine acts on.
 */
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

import type { DroidRun, HouseRuleStatus } from "@trophy/contracts";

export interface RunSink {
  update(run: DroidRun): Promise<void> | void;
}

export class JsonlSink implements RunSink {
  private readonly path: string;
  constructor(path: string) {
    this.path = path;
    mkdirSync(dirname(path), { recursive: true });
  }
  update(run: DroidRun): void {
    appendFileSync(this.path, JSON.stringify(run) + "\n");
  }
}

export class ConsoleSink implements RunSink {
  private seen = 0;
  update(run: DroidRun): void {
    for (const s of run.steps.slice(this.seen)) {
      const t = (s.t_ms / 1000).toFixed(1).padStart(6);
      process.stderr.write(`${t}s ${s.kind.padEnd(8)} ${s.text}\n`);
    }
    this.seen = run.steps.length;
    if (run.status === "ready" || run.status === "failed") {
      process.stderr.write(
        `${(run.duration_ms ?? 0) / 1000}s ${run.status.toUpperCase()}${run.error ? `: ${run.error}` : ""}\n`,
      );
    }
  }
}

export class MultiSink implements RunSink {
  private readonly sinks: RunSink[];
  constructor(sinks: RunSink[]) {
    this.sinks = sinks;
  }
  async update(run: DroidRun): Promise<void> {
    for (const s of this.sinks) await s.update(run);
  }
}

export type ReducerCall = (reducer: string, payload: unknown) => Promise<void>;

/**
 * Reducer calls in order, one at a time, errors logged (never thrown): the runner emits without awaiting, so two
 * snapshots could otherwise race and the older one be refused as stale, or reject unhandled and kill the process.
 * Snapshots that queue up while a call is in flight collapse to the newest.
 */
export class Serial {
  private chain: Promise<void> = Promise.resolve();
  private pending: (() => Promise<void>) | null = null;
  private readonly label: string;
  private readonly log: (msg: string) => void;
  constructor(label: string, log: (msg: string) => void = (m) => process.stderr.write(`${m}\n`)) {
    this.label = label;
    this.log = log;
  }
  push(fn: () => Promise<void>, collapse = true): Promise<void> {
    if (collapse) {
      const queued = this.pending !== null;
      this.pending = fn; // the newest snapshot replaces one still waiting
      if (queued) return this.chain;
      return this.run(() => {
        const f = this.pending;
        this.pending = null;
        return f ? f() : Promise.resolve();
      });
    }
    return this.run(fn);
  }
  private run(fn: () => Promise<void>): Promise<void> {
    this.chain = this.chain.then(async () => {
      try {
        await fn();
      } catch (e) {
        this.log(`${this.label}: ${(e as Error).message}`);
      }
    });
    return this.chain;
  }
}

/** Every run, any kind, as a droid_run row (compiler identity). */
export class DroidRunSpacetimeSink implements RunSink {
  private readonly call: ReducerCall;
  private readonly q = new Serial("update_droid_run");
  constructor(call: ReducerCall) {
    this.call = call;
  }
  update(run: DroidRun): Promise<void> {
    const snap = structuredClone(run);
    return this.q.push(() => this.call("update_droid_run", snap));
  }
}

/** Mirrors a house-rule run into Spacetime's house_rule row (compiler identity). */
export class HouseRuleSpacetimeSink implements RunSink {
  private sentSteps = 0;
  private readonly call: ReducerCall;
  private readonly ruleVersion: string;
  private readonly q = new Serial("update_house_rule_progress");
  constructor(call: ReducerCall, ruleVersion: string) {
    this.call = call;
    this.ruleVersion = ruleVersion;
  }
  update(run: DroidRun): Promise<void> {
    const patch = this.patch(run);
    // steps are appended, so every patch must arrive: no collapsing
    return this.q.push(() => this.call("update_house_rule_progress", patch), false);
  }
  patch(run: DroidRun): Record<string, unknown> {
    const status: HouseRuleStatus | undefined =
      run.status === "running"
        ? "compiling"
        : run.status === "ready"
          ? "ready"
          : run.status === "failed"
            ? "failed"
            : undefined;
    const patch: Record<string, unknown> = {
      rule_version: this.ruleVersion,
      backend: run.backend,
      plan_md: run.plan_md,
      diff: run.diff,
      results: run.results ? { tests: run.results.tests, calls_changed: run.results.calls_changed } : null,
      append_steps: run.steps.slice(this.sentSteps),
      error: run.error ?? null,
      pack_path: run.commit ? `${run.workspace}/sports/${run.sport}/rules.yaml@${run.commit}` : null,
      run_id: run.run_id,
      decision: run.decision ? { ...run.decision, decided_by: "droid" } : null,
    };
    if (run.results) (patch.results as Record<string, unknown>).passed = run.results.passed;
    if (status) patch.status = status;
    this.sentSteps = run.steps.length;
    return patch;
  }
}

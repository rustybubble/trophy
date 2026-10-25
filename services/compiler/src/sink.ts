/**
 * Where a run's live state goes. `DroidRun` (droidrun.schema.json) is the row the dashboard renders; every sink gets
 * the full row on each change. JSONL keeps the history on disk; Spacetime mirrors house-rule runs into the house_rule
 * row through update_house_rule_progress (the reducer that exists today) and will post droid_run rows once Agent 1
 * adds that table.
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

/** Mirrors a house-rule run into Spacetime's house_rule row (compiler identity). */
export class HouseRuleSpacetimeSink implements RunSink {
  private sentSteps = 0;
  private readonly call: ReducerCall;
  private readonly ruleVersion: string;
  constructor(call: ReducerCall, ruleVersion: string) {
    this.call = call;
    this.ruleVersion = ruleVersion;
  }
  async update(run: DroidRun): Promise<void> {
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
    };
    if (status) patch.status = status;
    this.sentSteps = run.steps.length;
    await this.call("update_house_rule_progress", patch);
  }
}

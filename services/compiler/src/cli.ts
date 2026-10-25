#!/usr/bin/env -S npx tsx
/**
 * trophy-droid: the Factory Droid compiler from the command line.
 *
 *   trophy-droid compile    --sport pickleball --from table_tennis --scene <scene.json> --samples <dir>
 *   trophy-droid house-rule --sport table_tennis --text "a serve that clips the net is a let" --samples <dir> [--rule-version <ulid> --spacetime]
 *                           [--base-pack <rules.yaml> --session <session.json>]   # the engine's snapshot (D-43)
 *   trophy-droid interpreter --sport badminton [--fixtures <dir>] [--samples <dir>] [--game-id <g> --spacetime]
 *                           # D-43: write the sport's let/out/fault rules.yaml, gated on evals/fixtures/annotated/<sport>
 *   trophy-droid retune     --sport table_tennis --reason "ball lost in 45% of frames" --scene <scene.json> --samples <dir>
 *   trophy-droid calibrate  --sport table_tennis --field <field.json> --samples <dir> [--checks <dir>] [--session <id>]
 *   trophy-droid new-check  --sport table_tennis --name ball_speed --question "how fast was that" --hint "..."
 *                           --session-track <track3d.jsonl> --session-field <field.json> --query '{"t0":1,"t1":4}'
 *                           # the referee's request_check: write one check, gate it on the session's own track
 *                                                        # D-36: specialise sports/<sport>/checks to this calibration
 *   trophy-droid watch      [--ws ws://127.0.0.1:3000]   # the Droid's triggers: pending house rules and queued
 *                                                        # interpreter requests (droid_run); every run -> droid_run
 *   trophy-droid approve    <run_id> [--by judge] [--session <id>]
 *                           # module runs: promote to data/local/modules/<sport>/v<n>
 *                           # calibrate runs: install the checks in data/local/sessions/<session|run_id>/checks
 *
 * Every run streams to stderr and to ~/.trophy/droid_runs/<run_id> (DROID_RUNS_DIR)/run.jsonl (the job as job.json beside it); the
 * sandbox stays as the artifact.
 */
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { parseArgs } from "node:util";

import type { DroidRun, HouseRule, SportModuleRow } from "@trophy/contracts";

import { approveChecks } from "./approve.ts";
import { ConfigError, loadConfig, REPO_ROOT } from "./config.ts";
import { droidAgentFactory } from "./droidAgent.ts";
import { runJob } from "./runner.ts";
import type { Job } from "./sandbox.ts";
import {
  ConsoleSink,
  DroidRunSpacetimeSink,
  HouseRuleSpacetimeSink,
  JsonlSink,
  MultiSink,
  type RunSink,
} from "./sink.ts";
import { reducerCaller, watchDroidTriggers } from "./spacetime.ts";

function usage(): never {
  process.stderr.write(
    readFileSync(new URL(import.meta.url), "utf8")
      .split("*/")[0]!
      .replace(/^\/\*\*\s*\n|^ \* ?/gm, "") + "\n",
  );
  process.exit(2);
}

async function runOne(job: Job, extra: RunSink[] = []): Promise<DroidRun> {
  const config = loadConfig();
  const run = await runJob(job, {
    config,
    agentFactory: droidAgentFactory({ apiKey: config.factoryApiKey, execPath: config.droidExecPath }),
    sink: new MultiSink([new ConsoleSink(), new LazyJsonl(config.runsDir), ...extra]),
  });
  // approve needs what the run row does not carry (session id, field path); the job is small and has no secrets
  writeFileSync(join(config.runsDir, run.run_id, "job.json"), JSON.stringify(job, null, 1) + "\n");
  process.stdout.write(
    JSON.stringify(
      {
        run_id: run.run_id,
        status: run.status,
        attempts: run.attempt,
        duration_ms: run.duration_ms,
        gate_ms: run.gate_ms,
        commit: run.commit,
        workspace: run.workspace,
        error: run.error,
        blocked: run.blocked,
        decision: run.decision,
      },
      null,
      1,
    ) + "\n",
  );
  return run;
}

/** The run id is only known once the run starts, so the JSONL sink opens on first update. */
class LazyJsonl implements RunSink {
  private inner: JsonlSink | undefined;
  private readonly runsDir: string;
  constructor(runsDir: string) {
    this.runsDir = runsDir;
  }
  update(run: DroidRun): void {
    this.inner ??= new JsonlSink(join(this.runsDir, run.run_id, "run.jsonl"));
    this.inner.update(run);
  }
}

async function main(argv: string[]): Promise<number> {
  const [cmd, ...rest] = argv;
  const { values, positionals } = parseArgs({
    args: rest,
    allowPositionals: true,
    options: {
      sport: { type: "string" },
      from: { type: "string", default: "table_tennis" },
      scene: { type: "string" },
      samples: { type: "string" },
      text: { type: "string" },
      reason: { type: "string" },
      "rule-version": { type: "string" },
      "game-id": { type: "string" },
      spacetime: { type: "boolean", default: false },
      ws: { type: "string", default: "ws://127.0.0.1:3000" },
      by: { type: "string", default: "judge" },
      field: { type: "string" },
      name: { type: "string" },
      question: { type: "string" },
      hint: { type: "string" },
      "session-track": { type: "string" },
      "session-field": { type: "string" },
      query: { type: "string", default: "{}" },
      checks: { type: "string" },
      session: { type: "string" },
      fixtures: { type: "string" },
      "base-pack": { type: "string" },
    },
  });
  const samplesFor = (sport: string) => values.samples ?? join(REPO_ROOT, "evals/fixtures/synthetic", sport);
  switch (cmd) {
    case "compile": {
      if (!values.sport) usage();
      const sport = values.sport;
      const scene = values.scene ?? join(samplesFor(sport), "scene.json");
      const run = await runOne({
        kind: "compile",
        sport,
        baseSport: values.from,
        scene,
        samplesDir: samplesFor(sport),
      });
      return run.status === "ready" ? 0 : 1;
    }
    case "interpreter": {
      if (!values.sport) usage();
      const extra: RunSink[] = values.spacetime ? [new DroidRunSpacetimeSink(reducerCaller(loadConfig()))] : [];
      const run = await runOne(
        {
          kind: "interpreter",
          sport: values.sport,
          samplesDir: samplesFor(values.sport),
          fixturesDir: values.fixtures,
          gameId: values["game-id"],
          triggerSource: "cli",
          text: values.text,
        },
        extra,
      );
      return run.status === "ready" ? 0 : 1;
    }
    case "house-rule": {
      if (!values.sport || !values.text) usage();
      const extra: RunSink[] = [];
      if (values.spacetime) {
        if (!values["rule-version"])
          throw new ConfigError("--spacetime needs --rule-version (the house_rule row to update)");
        const call = reducerCaller(loadConfig());
        extra.push(new HouseRuleSpacetimeSink(call, values["rule-version"]), new DroidRunSpacetimeSink(call));
      }
      const run = await runOne(
        {
          kind: "house_rule",
          sport: values.sport,
          text: values.text,
          samplesDir: samplesFor(values.sport),
          ruleVersion: values["rule-version"],
          gameId: values["game-id"],
          basePack: values["base-pack"],
          session: values.session,
        },
        extra,
      );
      return run.status === "ready" ? 0 : 1;
    }
    case "retune": {
      if (!values.sport || !values.reason) usage();
      const sport = values.sport;
      const run = await runOne({
        kind: "retune",
        sport,
        text: values.reason,
        scene: values.scene ?? join(samplesFor(sport), "scene.json"),
        samplesDir: samplesFor(sport),
      });
      return run.status === "ready" ? 0 : 1;
    }
    case "calibrate": {
      if (!values.sport) usage();
      const sport = values.sport;
      const samplesDir = values.samples ?? join(REPO_ROOT, "evals/fixtures/synthetic", `${sport}_3d`);
      const run = await runOne({
        kind: "calibrate_checks",
        sport,
        fieldPath: values.field ?? join(samplesDir, "field.json"),
        samplesDir,
        checksDir: values.checks,
        sessionId: values.session,
        gameId: values["game-id"],
      });
      return run.status === "ready" ? 0 : 1;
    }
    case "new-check": {
      // the engine starts this for the referee's request_check (interfaces-v1 section 20); prints the run JSON
      if (!values.sport || !values.name || !values.question || !values["session-track"]) usage();
      const sport = values.sport;
      const samplesDir = values.samples ?? join(REPO_ROOT, "evals/fixtures/synthetic", `${sport}_3d`);
      const run = await runOne({
        kind: "new_check",
        sport,
        text: values.question,
        fieldPath: values.field ?? join(samplesDir, "field.json"),
        samplesDir,
        checksDir: values.checks,
        sessionId: values.session,
        gameId: values["game-id"],
        newCheck: {
          name: values.name,
          question: values.question,
          hint: values.hint,
          sessionTrack: values["session-track"],
          sessionField: values["session-field"] ?? values.field ?? join(samplesDir, "field.json"),
          query: JSON.parse(values.query) as Record<string, unknown>,
        },
      });
      return run.status === "ready" ? 0 : 1;
    }
    case "watch": {
      const config = loadConfig();
      const call = reducerCaller(config);
      const seen = new Set<string>();
      const fail = (e: unknown) => process.stderr.write(`run failed: ${(e as Error).message}\n`);
      const watcher = await watchDroidTriggers(values.ws, config.spacetimeModule, {
        houseRule: (h: HouseRule) => {
          if (seen.has(h.rule_version)) return;
          seen.add(h.rule_version);
          process.stderr.write(`house_rule ${h.rule_version} (${h.sport}): ${h.text}\n`);
          void runOne(
            {
              kind: "house_rule",
              sport: h.sport,
              text: h.text,
              samplesDir: samplesFor(h.sport),
              ruleVersion: h.rule_version,
              gameId: h.game_id,
              // D-43: start from the pack in force (rules stack) and gate against this game's own events
              basePack: h.base_pack_path ?? undefined,
              session: h.session_path ?? undefined,
            },
            [new HouseRuleSpacetimeSink(call, h.rule_version), new DroidRunSpacetimeSink(call)],
          ).catch(fail);
        },
        runRequest: (r: DroidRun) => {
          if (seen.has(r.run_id)) return;
          seen.add(r.run_id);
          process.stderr.write(
            `droid_run ${r.run_id} (${r.kind} ${r.sport}, ${r.trigger.source}): ${r.trigger.text ?? ""}\n`,
          );
          void runOne(
            {
              kind: "interpreter",
              sport: r.sport,
              samplesDir: samplesFor(r.sport),
              gameId: r.game_id ?? undefined,
              runId: r.run_id,
              triggerSource: r.trigger.source === "user" ? "user" : "sport_module",
              text: r.trigger.text,
            },
            [new DroidRunSpacetimeSink(call)],
          ).catch(fail);
        },
      });
      process.stderr.write(
        `watching ${values.ws} ${config.spacetimeModule} for pending house rules and interpreter requests (ctrl-c to stop)\n`,
      );
      await new Promise<void>((resolve) =>
        process.once("SIGINT", () => {
          watcher.close();
          resolve();
        }),
      );
      return 0;
    }
    case "approve": {
      const runId = positionals[0];
      if (!runId) usage();
      const config = loadConfig();
      const log = join(config.runsDir, runId, "run.jsonl");
      if (!existsSync(log)) throw new Error(`no run ${runId} under ${config.runsDir}`);
      const lines = readFileSync(log, "utf8").trim().split("\n");
      const run = JSON.parse(lines[lines.length - 1]!) as DroidRun;
      if (run.status !== "ready") throw new Error(`run ${runId} is ${run.status}, not ready`);
      if (run.kind === "calibrate_checks") {
        const row = approveChecks(run, runId, values.session, values.by, join(config.runsDir, runId));
        new JsonlSink(log).update({
          ...run,
          status: "approved",
          module_version: row.version,
          updated_at_ms: Date.now(),
        });
        process.stdout.write(JSON.stringify(row, null, 1) + "\n");
        return 0;
      }
      const modulesDir = join(REPO_ROOT, "data/local/modules", run.sport);
      mkdirSync(modulesDir, { recursive: true });
      const version = readdirSync(modulesDir).filter((d) => /^v\d+$/.test(d)).length + 1;
      const dest = join(modulesDir, `v${version}`);
      cpSync(join(run.workspace!, "sports", run.sport), dest, { recursive: true });
      const row: SportModuleRow = {
        sport: run.sport,
        version,
        backend: "droid",
        run_id: runId,
        path: dest,
        commit: run.commit ?? undefined,
        game_id: run.game_id ?? null,
        approved_at_ms: Date.now(),
        approved_by: values.by,
      };
      writeFileSync(join(dest, "sport_module.json"), JSON.stringify(row, null, 1) + "\n");
      new JsonlSink(log).update({ ...run, status: "approved", module_version: version, updated_at_ms: Date.now() });
      process.stdout.write(JSON.stringify(row, null, 1) + "\n");
      return 0;
    }
    default:
      usage();
  }
}

main(process.argv.slice(2)).then(
  (code) => process.exit(code),
  (e) => {
    process.stderr.write(`${e instanceof ConfigError ? "config: " : ""}${(e as Error).message}\n`);
    process.exit(e instanceof ConfigError ? 3 : 1);
  },
);

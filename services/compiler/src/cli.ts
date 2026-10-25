#!/usr/bin/env -S npx tsx
/**
 * trophy-droid: the Factory Droid compiler from the command line.
 *
 *   trophy-droid compile    --sport pickleball --from table_tennis --scene <scene.json> --samples <dir>
 *   trophy-droid house-rule --sport table_tennis --text "a serve that clips the net is a let" --samples <dir> [--rule-version <ulid> --spacetime]
 *   trophy-droid retune     --sport table_tennis --reason "ball lost in 45% of frames" --scene <scene.json> --samples <dir>
 *   trophy-droid watch      [--ws ws://127.0.0.1:3000]   # subscribe to pending house rules and compile each one
 *   trophy-droid approve    <run_id> [--by judge]         # promote a ready run to data/local/modules/<sport>/v<n>
 *
 * Every run streams to stderr and to data/local/droid_runs/<run_id>/run.jsonl; the sandbox stays as the artifact.
 */
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { parseArgs } from "node:util";

import type { DroidRun, HouseRule, SportModuleRow } from "@trophy/contracts";

import { ConfigError, loadConfig, REPO_ROOT } from "./config.ts";
import { droidAgentFactory } from "./droidAgent.ts";
import { runJob } from "./runner.ts";
import type { Job } from "./sandbox.ts";
import { ConsoleSink, HouseRuleSpacetimeSink, JsonlSink, MultiSink, type RunSink } from "./sink.ts";
import { reducerCaller, watchPendingHouseRules } from "./spacetime.ts";

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
    case "house-rule": {
      if (!values.sport || !values.text) usage();
      const extra: RunSink[] = [];
      if (values.spacetime) {
        if (!values["rule-version"])
          throw new ConfigError("--spacetime needs --rule-version (the house_rule row to update)");
        extra.push(new HouseRuleSpacetimeSink(reducerCaller(loadConfig()), values["rule-version"]));
      }
      const run = await runOne(
        {
          kind: "house_rule",
          sport: values.sport,
          text: values.text,
          samplesDir: samplesFor(values.sport),
          ruleVersion: values["rule-version"],
          gameId: values["game-id"],
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
    case "watch": {
      const config = loadConfig();
      const call = reducerCaller(config);
      const seen = new Set<string>();
      const watcher = await watchPendingHouseRules(values.ws, config.spacetimeModule, (h: HouseRule) => {
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
          },
          [new HouseRuleSpacetimeSink(call, h.rule_version)],
        ).catch((e) => process.stderr.write(`run failed: ${(e as Error).message}\n`));
      });
      process.stderr.write(
        `watching ${values.ws} ${config.spacetimeModule} for pending house rules (ctrl-c to stop)\n`,
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

/** Run the test gate ourselves (never trust the agent's account of it) and parse its JSON. */
import { execFile } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";

import type { DroidRunResults } from "@trophy/contracts";

export interface GateOutcome {
  results: DroidRunResults;
  stdout: string;
  exitCode: number;
  ms: number;
}

/** `script` is the gate's file name in the sandbox (`replay_test` | `check_test`). */
export function runGate(sandboxDir: string, script = "replay_test", timeoutMs = 60_000): Promise<GateOutcome> {
  const resultsPath = join(sandboxDir, ".trophy", "results.json");
  rmSync(resultsPath, { force: true });
  const t0 = Date.now();
  return new Promise((resolve, reject) => {
    execFile(
      join(sandboxDir, script),
      [],
      {
        cwd: sandboxDir,
        timeout: timeoutMs,
        encoding: "utf8",
        maxBuffer: 8 << 20,
        env: { PATH: process.env.PATH ?? "", HOME: process.env.HOME ?? "" },
      },
      (err, stdout, stderr) => {
        const ms = Date.now() - t0;
        const exitCode =
          err && typeof (err as NodeJS.ErrnoException & { code?: unknown }).code === "number"
            ? (err as { code: number }).code
            : err
              ? 2
              : 0;
        if (!existsSync(resultsPath)) {
          reject(new Error(`${script} produced no results (exit ${exitCode}): ${stderr || stdout}`.slice(0, 2000)));
          return;
        }
        const results = JSON.parse(readFileSync(resultsPath, "utf8")) as DroidRunResults;
        resolve({ results, stdout: String(stdout), exitCode, ms });
      },
    );
  });
}

export function formatTestTable(r: DroidRunResults): string {
  const w = Math.max(5, ...r.tests.map((t) => t.name.length));
  const lines = r.tests.map(
    (t) =>
      `${t.name.padEnd(w)}  ${(t.before ?? "").padEnd(14)}  ${t.after ?? ""}  [${t.pass ? "PASS" : "FAIL"}]${t.pass || !t.detail ? "" : `\n${"".padEnd(w)}  ${t.detail}`}`,
  );
  return [`${"check".padEnd(w)}  ${"before".padEnd(14)}  after`, ...lines, r.summary].join("\n");
}

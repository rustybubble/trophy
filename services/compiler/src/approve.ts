/** Approval of a ready calibrate_checks run: the checks become the session's library (D-36). */
import { createHash } from "node:crypto";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import type { DroidRun, SportModuleRow } from "@trophy/contracts";

import { REPO_ROOT } from "./config.ts";
import type { Job } from "./sandbox.ts";

/**
 * Install a ready calibrate_checks run as the session's library (D-36): data/local/sessions/<session>/checks/, with
 * library.json flipped to calibrated: true (the engine reads that flag) and the usual SportModuleRow beside it.
 * The session id comes from --session, else the job that started the run, else the run id.
 */
export function approveChecks(
  run: DroidRun,
  runId: string,
  sessionArg: string | undefined,
  by: string,
  runDir: string,
  root = REPO_ROOT,
): SportModuleRow {
  const jobPath = join(runDir, "job.json");
  const job = existsSync(jobPath) ? (JSON.parse(readFileSync(jobPath, "utf8")) as Partial<Job>) : {};
  const sessionId = sessionArg ?? job.sessionId ?? runId;
  const src = join(run.workspace!, "checks");
  if (!existsSync(src)) throw new Error(`run ${runId}: no checks/ in ${run.workspace}`);
  const dest = join(root, "data/local/sessions", sessionId, "checks");
  rmSync(dest, { recursive: true, force: true }); // a new calibration replaces the session's library
  mkdirSync(dest, { recursive: true });
  cpSync(src, dest, { recursive: true, filter: (p) => !/__pycache__/.test(p) });
  const fieldInSandbox = join(run.workspace!, "samples", "field.json");
  // the same resolution as the sandbox: an explicit field, else the one next to the samples, else the sandbox copy
  const fieldPath = job.fieldPath ?? (job.samplesDir ? join(job.samplesDir, "field.json") : fieldInSandbox);
  const fieldSha = existsSync(fieldInSandbox)
    ? createHash("sha256").update(readFileSync(fieldInSandbox)).digest("hex")
    : null;
  const approvedAt = Date.now();
  const row: SportModuleRow = {
    sport: run.sport,
    version: 1, // one library per session; a new calibration is a new run that replaces it
    backend: "droid",
    run_id: runId,
    path: dest,
    commit: run.commit ?? undefined,
    game_id: run.game_id ?? null,
    approved_at_ms: approvedAt,
    approved_by: by,
  };
  writeFileSync(
    join(dest, "library.json"),
    JSON.stringify(
      {
        calibrated: true,
        run_id: runId,
        session_id: sessionId,
        field: fieldPath,
        field_sha256: fieldSha,
        approved_at_ms: approvedAt,
        approved_by: by,
      },
      null,
      1,
    ) + "\n",
  );
  writeFileSync(join(dest, "sport_module.json"), JSON.stringify(row, null, 1) + "\n");
  return row;
}

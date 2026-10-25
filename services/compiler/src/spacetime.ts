/**
 * Spacetime: reducer calls (compiler identity) and the Droid's triggers: pending house_rule rows (a judge's rule, by
 * voice or typing) and queued droid_run requests the engine inserts (an interpreter for a sport that has none, or the
 * judge's "Regenerate interpreter").
 */
import type { DroidRun, HouseRule } from "@trophy/contracts";

import { DbConnection } from "../../../packages/state-client/src/bindings/index.ts";
import type { CompilerConfig } from "./config.ts";
import type { ReducerCall } from "./sink.ts";

export function reducerCaller(cfg: CompilerConfig): ReducerCall {
  if (!cfg.spacetimeCompilerToken) {
    throw new Error("SPACETIME_COMPILER_TOKEN is not set (run spacetime/scripts/provision.py)");
  }
  return async (reducer, payload) => {
    const res = await fetch(`${cfg.spacetimeUri}/v1/database/${cfg.spacetimeModule}/call/${reducer}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${cfg.spacetimeCompilerToken}`, "Content-Type": "application/json" },
      body: JSON.stringify([JSON.stringify(payload)]),
    });
    if (!res.ok) throw new Error(`${reducer}: HTTP ${res.status} ${await res.text()}`);
  };
}

export interface Watcher {
  close(): void;
}

/** A queued droid_run the compiler should start: requested by the engine, never touched by a runner yet. */
export function isRunRequest(r: DroidRun): boolean {
  return (
    r.status === "queued" &&
    r.kind === "interpreter" &&
    r.trigger?.requested_by === "engine" &&
    (r.trigger.source === "sport_module" || r.trigger.source === "user") &&
    r.attempt === 0 &&
    !r.workspace
  );
}

/**
 * Subscribe to `house_rule WHERE status = 'pending'` and `droid_run WHERE status = 'queued'`; the callbacks fire for
 * existing rows and every new one (house rules: status pending; runs: isRunRequest).
 */
export function watchDroidTriggers(
  wsUri: string,
  module: string,
  on: { houseRule: (h: HouseRule) => void; runRequest: (r: DroidRun) => void },
): Promise<Watcher> {
  return new Promise((resolve, reject) => {
    const uri = wsUri.endsWith("/") ? wsUri : `${wsUri}/`;
    const conn = DbConnection.builder()
      .withUri(uri)
      .withDatabaseName(module)
      .onConnect((c) => {
        type Tbl = { onInsert(cb: (ctx: unknown, row: { json: string }) => void): void };
        const db = c.db as unknown as { houseRule: Tbl; droidRun: Tbl };
        db.houseRule.onInsert((_ctx, row) => {
          const h = JSON.parse(row.json) as HouseRule;
          if (h.status === "pending") on.houseRule(h);
        });
        db.droidRun.onInsert((_ctx, row) => {
          const r = JSON.parse(row.json) as DroidRun;
          if (isRunRequest(r)) on.runRequest(r);
        });
        c.subscriptionBuilder()
          .onApplied(() => resolve({ close: () => conn.disconnect() }))
          .onError((ctx) => reject(new Error(`subscription error: ${String((ctx as { event?: unknown }).event)}`)))
          .subscribe([
            "SELECT * FROM house_rule WHERE status = 'pending'",
            "SELECT * FROM droid_run WHERE status = 'queued'",
          ]);
      })
      .onConnectError((_ctx, err) => reject(err instanceof Error ? err : new Error(String(err))))
      .build();
  });
}

/** Subscribe to `house_rule WHERE status = 'pending'`; `onPending` fires for existing rows and every new one. */
export function watchPendingHouseRules(
  wsUri: string,
  module: string,
  onPending: (h: HouseRule) => void,
): Promise<Watcher> {
  return new Promise((resolve, reject) => {
    const uri = wsUri.endsWith("/") ? wsUri : `${wsUri}/`;
    const conn = DbConnection.builder()
      .withUri(uri)
      .withDatabaseName(module)
      .onConnect((c) => {
        const db = c.db as unknown as {
          houseRule: { onInsert(cb: (ctx: unknown, row: { json: string }) => void): void };
        };
        db.houseRule.onInsert((_ctx, row) => {
          const h = JSON.parse(row.json) as HouseRule;
          if (h.status === "pending") onPending(h);
        });
        c.subscriptionBuilder()
          .onApplied(() => resolve({ close: () => conn.disconnect() }))
          .onError((ctx) => reject(new Error(`subscription error: ${String((ctx as { event?: unknown }).event)}`)))
          .subscribe(["SELECT * FROM house_rule WHERE status = 'pending'"]);
      })
      .onConnectError((_ctx, err) => reject(err instanceof Error ? err : new Error(String(err))))
      .build();
  });
}

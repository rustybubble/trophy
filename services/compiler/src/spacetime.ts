/** Spacetime: reducer calls (compiler identity) and the pending house_rule subscription (the Droid's trigger). */
import type { HouseRule } from "@trophy/contracts";

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

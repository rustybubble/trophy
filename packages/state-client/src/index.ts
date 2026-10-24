import { MockState, type MockOptions } from "./mock.ts";
import { SpacetimeState } from "./spacetime.ts";
import type { MockScript, TrophyState } from "./types.ts";

export * from "./types.ts";
export { MockState, type MockOptions } from "./mock.ts";
export { SpacetimeState, type SpacetimeOptions } from "./spacetime.ts";

export interface CreateStateOptions extends MockOptions {
  /** Spacetime URI, e.g. wss://<domain>/stdb (spacetime) */
  uri?: string;
  /** Spacetime module name (spacetime) */
  module?: string;
  /** Reject connect() after this many ms without an applied subscription (spacetime) */
  timeoutMs?: number;
  /** The synthetic script to play (mock) */
  script?: MockScript;
}

export function createState(impl: "mock" | "spacetime" | "ws", opts: CreateStateOptions = {}): TrophyState {
  switch (impl) {
    case "mock":
      if (!opts.script) throw new Error("createState('mock') needs opts.script (see @trophy/state-client/fixtures)");
      return new MockState(opts.script, opts);
    case "spacetime":
      if (!opts.uri) throw new Error("createState('spacetime') needs opts.uri (e.g. wss://trophy.photo/stdb)");
      return new SpacetimeState({
        uri: opts.uri,
        module: opts.module ?? "trophy",
        ...(opts.timeoutMs ? { timeoutMs: opts.timeoutMs } : {}),
      });
    case "ws":
      // OPEN-1 fallback (an engine-side WebSocket fan-out); not needed while Spacetime works.
      throw new Error("createState('ws') is not implemented yet; use 'spacetime' or 'mock'");
  }
}

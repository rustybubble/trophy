import { MockState, type MockOptions } from "./mock.ts";
import type { MockScript, TrophyState } from "./types.ts";

export * from "./types.ts";
export { MockState, type MockOptions } from "./mock.ts";

export interface CreateStateOptions extends MockOptions {
  /** Spacetime URI, e.g. wss://<domain>/stdb (spacetime) */
  uri?: string;
  /** Spacetime module name (spacetime) */
  module?: string;
  /** The synthetic script to play (mock) */
  script?: MockScript;
}

export function createState(impl: "mock" | "spacetime" | "ws", opts: CreateStateOptions = {}): TrophyState {
  switch (impl) {
    case "mock":
      if (!opts.script) throw new Error("createState('mock') needs opts.script (see @trophy/state-client/fixtures)");
      return new MockState(opts.script, opts);
    case "spacetime":
    case "ws":
      // SpacetimeState lands with the Spacetime module in P1 (interfaces-v1 §11); "ws" is the OPEN-1 fallback.
      throw new Error(`createState('${impl}') is not implemented yet; use 'mock' until P1`);
  }
}

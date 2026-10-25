// SpacetimeState's connection retries, against a scripted stand-in for the generated DbConnection (no server).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Cb = (...args: unknown[]) => void;
interface Fake {
  uri: string;
  reconnect: boolean;
  disconnected: boolean;
  on: Record<string, Cb>;
  /** the server answers: the socket opens and both subscriptions apply */
  open(rows?: Record<string, object[]>): void;
}
const conns: Fake[] = [];

vi.mock("../src/bindings/index.ts", () => {
  const table = () => {
    const h: Record<string, Cb[]> = { insert: [], update: [], delete: [] };
    return {
      h,
      onInsert: (cb: Cb) => h.insert!.push(cb),
      onUpdate: (cb: Cb) => h.update!.push(cb),
      onDelete: (cb: Cb) => h.delete!.push(cb),
    };
  };
  const builder = () => {
    const f: Fake = {
      uri: "",
      reconnect: false,
      disconnected: false,
      on: {},
      open(rows = {}) {
        const db: Record<string, ReturnType<typeof table>> = new Proxy(
          {},
          { get: (t: Record<string, ReturnType<typeof table>>, k: string) => (t[k] ??= table()) },
        );
        const applied: Cb[] = [];
        const conn = {
          db,
          disconnect: () => (f.disconnected = true),
          subscriptionBuilder() {
            const sb = {
              onApplied: (cb: Cb) => (applied.push(cb), sb),
              onError: () => sb,
              subscribe: () => undefined,
            };
            return sb;
          },
        };
        f.on.connect!(conn);
        for (const [accessor, list] of Object.entries(rows))
          for (const row of list) db[accessor]!.h.insert!.forEach((cb) => cb({}, { json: JSON.stringify(row) }));
        applied.forEach((cb) => cb());
      },
    };
    conns.push(f);
    const b = {
      withUri: (u: string) => ((f.uri = u), b),
      withDatabaseName: () => b,
      withAutomaticReconnect: () => ((f.reconnect = true), b),
      onConnect: (cb: Cb) => ((f.on.connect = cb), b),
      onConnectError: (cb: Cb) => ((f.on.connectError = cb), b),
      onDisconnect: (cb: Cb) => ((f.on.disconnect = cb), b),
      build: () => ({ disconnect: () => (f.disconnected = true) }),
    };
    return b;
  };
  return { DbConnection: { builder } };
});

const { SpacetimeState } = await import("../src/spacetime.ts");
const GAME = "g_abcdefgh";
const game = { game_id: GAME, sport: "table_tennis", status: "live", t0_ms: 0, teams: [], params: {} };

describe("SpacetimeState retries", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    conns.length = 0;
  });
  afterEach(() => vi.useRealTimers());

  it("retries a socket that fails to open, then resolves (a tunnel hiccup is not fatal)", async () => {
    const s = new SpacetimeState({ uri: "wss://x.trycloudflare.com/stdb", module: "trophy", timeoutMs: 30000 });
    const p = s.connect(GAME);
    expect(conns).toHaveLength(1);
    expect(conns[0]!.uri).toBe("wss://x.trycloudflare.com/stdb/");
    expect(conns[0]!.reconnect).toBe(true);
    conns[0]!.on.connectError!({}, new Error("WebSocket error"));
    await vi.advanceTimersByTimeAsync(500);
    expect(conns).toHaveLength(2);
    conns[1]!.open({ game: [game] });
    await expect(p).resolves.toBeUndefined();
    expect(s.game()?.game_id).toBe(GAME);
    s.disconnect();
  });

  it("rejects at the timeout with the socket error but keeps retrying, so late rows still arrive", async () => {
    const s = new SpacetimeState({ uri: "wss://h/stdb", module: "trophy", timeoutMs: 3000 });
    const p = s.connect(GAME);
    const failed = expect(p).rejects.toThrow(/WebSocket error.*still retrying/);
    for (let i = 0; i < 4; i++) {
      conns.at(-1)!.on.connectError!({}, new Error("WebSocket error"));
      await vi.advanceTimersByTimeAsync(5000);
    }
    await failed;
    const before = conns.length;
    expect(before).toBeGreaterThan(3);
    conns.at(-1)!.open({ game: [game] });
    expect(s.game()?.game_id).toBe(GAME);
    s.disconnect();
  });

  it("starts a new connection when the SDK gives up on an established session", async () => {
    const s = new SpacetimeState({ uri: "wss://h/stdb", module: "trophy" });
    const p = s.connect(GAME);
    conns[0]!.open({ game: [game] });
    await p;
    // still reconnecting: the SDK owns it
    conns[0]!.on.disconnect!({}, new Error("WebSocket closed (code 1006)"), 1, 1000);
    conns[0]!.on.connectError!({}, new Error("WebSocket error"), 2, 2000);
    await vi.advanceTimersByTimeAsync(10000);
    expect(conns).toHaveLength(1);
    // gave up (no next attempt): a fresh connection
    conns[0]!.on.connectError!({}, new Error("WebSocket error"), undefined, undefined);
    await vi.advanceTimersByTimeAsync(500);
    expect(conns).toHaveLength(2);
    s.disconnect();
  });

  it("stops retrying after disconnect()", async () => {
    const s = new SpacetimeState({ uri: "wss://h/stdb", module: "trophy", timeoutMs: 1000 });
    const p = s.connect(GAME).catch(() => undefined);
    conns[0]!.on.connectError!({}, new Error("WebSocket error"));
    s.disconnect();
    await vi.advanceTimersByTimeAsync(10000);
    await p;
    expect(conns).toHaveLength(1);
  });
});

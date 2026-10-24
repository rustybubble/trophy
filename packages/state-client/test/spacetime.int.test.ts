// Integration test against a live local Spacetime module (skipped unless TROPHY_STDB_IT=1):
//   spacetime start; spacetime publish -s local -p spacetime trophy; python spacetime/scripts/provision.py
//   TROPHY_STDB_IT=1 SPACETIME_ENGINE_TOKEN=... SPACETIME_VISION_TOKEN=... npx vitest run --root packages/state-client
import { afterAll, describe, expect, it } from "vitest";
import { createState, type Call, type TrophyState } from "../src/index.ts";

const IT = process.env.TROPHY_STDB_IT === "1";
// reducers go straight to the server (as backend services do); the subscription can go through Caddy:
// TROPHY_STDB_WS=wss://trophy.photo/stdb
const HTTP = process.env.SPACETIME_URI ?? "http://127.0.0.1:3000";
const WS = process.env.TROPHY_STDB_WS ?? HTTP.replace(/^http/, "ws");
const MODULE = process.env.SPACETIME_MODULE ?? "trophy";
const CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz";
const rand = (n: number) => Array.from({ length: n }, () => CROCKFORD[Math.floor(Math.random() * 32)]).join("");

async function reducer(name: string, payload: unknown, role: "engine" | "vision"): Promise<void> {
  const token = process.env[`SPACETIME_${role.toUpperCase()}_TOKEN`];
  const res = await fetch(`${HTTP}/v1/database/${MODULE}/call/${name}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify([JSON.stringify(payload)]),
  });
  if (res.status !== 200) throw new Error(`${name}: HTTP ${res.status} ${await res.text()}`);
}

function until<T>(get: () => T | undefined, ms = 5000): Promise<T> {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    const tick = () => {
      const v = get();
      if (v !== undefined) return resolve(v);
      if (Date.now() - t0 > ms) return reject(new Error("timed out"));
      setTimeout(tick, 5);
    };
    tick();
  });
}

describe.skipIf(!IT)("SpacetimeState (live module)", () => {
  const states: TrophyState[] = [];
  afterAll(() => states.forEach((s) => s.disconnect()));
  const G = `g_${rand(8)}`;
  const callId = `01JIT${rand(21).toUpperCase()}`;
  const call: Call = {
    schema: "trophy.call.v1",
    id: callId,
    game_id: G,
    t_game_s: 4.6,
    rule_id: "edge_ball",
    rule_version: "table_tennis@1",
    kind: "edge_call",
    outcome: "edge_good",
    team_id: "B",
    p: 0.71,
    p_source: "geometry",
    tier: "BETA",
    shown: "challengeable",
    text: "Edge ball — good. Point B (71%)",
    speech: "Edge ball. Good. Point, B.",
    cue: { beep: "double", flash: "B" },
    event_ids: [],
    evidence: [{ cam_id: "c_itcam1", t0_s: 2, t1_s: 5 }],
    status: "final",
    created_at_ms: Date.now(),
  };

  it("streams engine and vision writes to a subscriber, and replays them to a late one", async () => {
    const s = createState("spacetime", { uri: WS, module: MODULE });
    states.push(s);
    await s.connect(G);
    const seen: [Call, string][] = [];
    s.onCall((c, ch) => seen.push([c, ch]));

    await reducer(
      "upsert_game",
      {
        game_id: G,
        sport: "table_tennis",
        pack_version: "table_tennis@1",
        status: "live",
        t0_ms: Date.now(),
        period_no: 1,
        rally_no: 0,
        teams: [
          { team_id: "A", name: "A" },
          { team_id: "B", name: "B" },
        ],
        params: { synthetic: true, label: "SYNTHETIC integration test" },
        created_at_ms: Date.now(),
      },
      "engine",
    );
    await until(() => s.game());
    expect(s.synthetic).toBe(true);

    const t0 = performance.now();
    await reducer("post_call", call, "engine");
    await until(() => seen.find(([c]) => c.id === callId));
    const latency = performance.now() - t0;
    console.log(`post_call -> onCall: ${latency.toFixed(1)} ms (includes the HTTP round trip)`);

    await reducer("update_call_status", { call_id: callId, status: "challenged" }, "engine");
    await until(() => seen.find(([c, ch]) => c.status === "challenged" && ch === "update"));

    await reducer(
      "post_observations",
      [
        {
          schema: "trophy.event.v1",
          id: `01JOB${rand(21).toUpperCase()}`,
          game_id: G,
          t_game_s: 4.4,
          sport: "table_tennis",
          type: "ball_dead",
          source: "synthetic",
          cams: ["c_itcam1"],
          conf: 0.9,
          payload: { reason: "floor" },
        },
      ],
      "vision",
    );
    let obs = 0;
    s.onObservation(() => obs++);
    await until(() => (obs > 0 ? true : undefined));

    // another game's rows must not leak into this subscription
    await reducer("post_call", { ...call, id: `01JOT${rand(21).toUpperCase()}`, game_id: `g_${rand(8)}` }, "engine");
    await new Promise((r) => setTimeout(r, 200));
    expect(s.calls().every((c) => c.game_id === G)).toBe(true);

    const late = createState("spacetime", { uri: WS, module: MODULE });
    states.push(late);
    await late.connect(G);
    expect(late.calls().map((c) => [c.id, c.status])).toEqual([[callId, "challenged"]]);
    expect(late.game()?.game_id).toBe(G);
  });

  it("rejects bad game ids before building SQL", async () => {
    const s = createState("spacetime", { uri: WS, module: MODULE });
    await expect(s.connect("g_x' OR '1'='1")).rejects.toThrow(/bad game_id/);
  });
});

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createState, type AiVote, type Call, type HouseRule, type MockScript, type Score } from "../src/index.ts";
import tt from "../fixtures/table-tennis-demo.json" with { type: "json" };
import bb from "../fixtures/basketball-demo.json" with { type: "json" };

const ttScript = tt as unknown as MockScript;

describe("MockState", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("is labelled synthetic", () => {
    const s = createState("mock", { script: ttScript });
    expect(s.synthetic).toBe(true);
    expect(s.label).toMatch(/SYNTHETIC/);
    expect((bb as unknown as MockScript).synthetic).toBe(true);
  });

  it("plays the table-tennis demo: calls, score, challenge, votes, house rule, ask", async () => {
    const s = createState("mock", { script: ttScript, speed: 10 });
    const calls: [Call, string][] = [];
    const votes: AiVote[] = [];
    const rules: HouseRule[] = [];
    let score: Score[] = [];
    let asks = 0;
    let obs = 0;
    let samples = 0;
    s.onCall((c, ch) => calls.push([c, ch]));
    s.onAiVote((v) => votes.push(v));
    s.onHouseRule((h) => rules.push(h));
    s.onScore((sc) => (score = sc));
    s.onAsk(() => asks++);
    s.onObservation(() => obs++);
    s.onTrackSample(() => samples++);
    await s.connect("g_abcdefgh");
    vi.advanceTimersByTime(60_000);

    expect(s.game()?.game_id).toBe("g_abcdefgh"); // rows are re-homed to the connected game
    expect(s.game()?.status).toBe("live");
    const edge = calls.filter(([c]) => c.rule_id === "edge_ball");
    expect(edge.map(([c, ch]) => [c.status, ch])).toEqual([
      ["final", "insert"],
      ["challenged", "update"],
      ["upheld", "update"],
    ]);
    expect(new Set(votes.map((v) => v.backend))).toEqual(new Set(["claude", "gemini", "bitdeer"]));
    expect(rules.map((r) => r.status)).toEqual(["pending", "compiling", "ready", "approved"]);
    expect(score.find((x) => x.team_id === "B")?.points).toBe(3);
    expect(asks).toBe(1);
    expect(obs).toBeGreaterThan(5);
    expect(samples).toBeGreaterThan(20);
  });

  it("replays known rows to late subscribers and stops on disconnect", async () => {
    const s = createState("mock", { script: ttScript, speed: 100 });
    await s.connect("");
    vi.advanceTimersByTime(100); // 10 s of script
    const late: Call[] = [];
    s.onCall((c) => late.push(c));
    expect(late.length).toBeGreaterThan(0);
    s.disconnect();
    const n = late.length;
    vi.advanceTimersByTime(60_000);
    expect(late.length).toBe(n);
  });

  it("rejects unimplemented backends clearly", () => {
    expect(() => createState("ws")).toThrow(/not implemented yet/);
    expect(() => createState("spacetime")).toThrow(/needs opts.uri/);
  });
});

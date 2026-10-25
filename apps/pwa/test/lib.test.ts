import { describe, expect, it } from "vitest";
import { tableCrop } from "../src/lib/crop.ts";
import { FLAG_CROP, FLAG_FIRST_AFTER_START, packFrame } from "../src/lib/frame.ts";
import { apply, invert3 } from "../src/lib/homography.ts";
import { parseIntent } from "../src/lib/intent.ts";
import { OnsetDetector } from "../src/lib/onset.ts";
import { pickSegments } from "../src/lib/recorder.ts";

describe("packFrame", () => {
  it("matches the 16-byte little-endian header in interfaces-v1 §5.1 (and trophy.framebus)", () => {
    const jpeg = new Uint8Array([0xff, 0xd8, 1, 2, 0xff, 0xd9]).buffer;
    const buf = packFrame(0x01020304, 1792868000123.25, jpeg, FLAG_FIRST_AFTER_START);
    const v = new DataView(buf);
    expect(buf.byteLength).toBe(22);
    expect([v.getUint8(0), v.getUint8(1), v.getUint16(2, true)]).toEqual([1, 2, 0]);
    expect(new Uint8Array(buf, 4, 4)).toEqual(new Uint8Array([4, 3, 2, 1]));
    expect(v.getFloat64(8, true)).toBe(1792868000123.25);
    expect(new Uint8Array(buf, 16)).toEqual(new Uint8Array(jpeg));
  });
});

describe("parseIntent", () => {
  it.each([
    ["Challenge!", { kind: "challenge" }],
    ["Trophy, I challenge that.", { kind: "challenge" }],
    ["undo", { kind: "undo" }],
    ["What's the score?", { kind: "score" }],
    ["House rule: first to 7, win by 1.", { kind: "house_rule", text: "first to 7, win by 1." }],
    [
      "add a rule a serve that clips the net is a let",
      { kind: "house_rule", text: "a serve that clips the net is a let" },
    ],
    ["Trophy, what's the rule on edge balls?", { kind: "ask", question: "what's the rule on edge balls?" }],
    ["  ", { kind: "none" }],
  ])("%s", (text, want) => {
    expect(parseIntent(text)).toEqual(want);
  });
});

describe("OnsetDetector", () => {
  it("fires on a sharp transient over background noise, once per refractory window", () => {
    const sr = 48000;
    const det = new OnsetDetector(sr);
    let seed = 1;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 0.004; // quiet noise
    const onsets: number[] = [];
    const clickAt = [sr * 1.5, sr * 1.52, sr * 2.25]; // the second is inside the 60 ms refractory window
    for (let block = 0; block < (sr * 3) / 128; block++) {
      const x = new Float32Array(128);
      for (let i = 0; i < 128; i++) {
        const n = block * 128 + i;
        let s = rnd();
        for (const c of clickAt) if (n >= c && n < c + 48) s += 0.6 * Math.exp(-(n - c) / 10) * (n % 2 ? 1 : -1);
        x[i] = s;
      }
      const o = det.process(x, block * 128);
      if (o) onsets.push(o.frame / sr);
    }
    expect(onsets).toHaveLength(2);
    expect(onsets[0]).toBeCloseTo(1.5, 2);
    expect(onsets[1]).toBeCloseTo(2.25, 2);
  });
});

describe("homography", () => {
  it("inverts and round-trips points", () => {
    const h = [0.004, 0.0001, -2.5, 0.0002, -0.005, 3.1, 0.00001, 0.00002, 1];
    const inv = invert3(h);
    const [fx, fy] = apply(h, 640, 400);
    const [x, y] = apply(inv, fx, fy);
    expect(x).toBeCloseTo(640, 6);
    expect(y).toBeCloseTo(400, 6);
  });
});

describe("pickSegments", () => {
  const seg = (index: number, t0: number, t1: number) => ({
    blob: new Blob(),
    mime: "video/mp4",
    tStartPhoneMs: t0,
    tEndPhoneMs: t1,
    index,
  });
  it("returns the segments overlapping a window, oldest first", () => {
    const segs = [seg(3, 18_000, 24_000), seg(1, 6_000, 12_000), seg(2, 12_020, 18_000), seg(0, 0, 6_000)];
    expect(pickSegments(segs, 11_000, 13_000).map((s) => s.index)).toEqual([1, 2]);
    expect(pickSegments(segs, 30_000, 31_000)).toEqual([]);
    expect(pickSegments(segs, 12_005, 12_010).map((s) => s.index)).toEqual([]); // inside the restart gap
  });
});

describe("table crop", () => {
  it("packs the crop after the header and sets FLAG_CROP (trophy.framebus.parse_message reads it)", () => {
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]).buffer;
    const buf = packFrame(5, 1, jpeg, 0, { x: 0.125, y: 0.25, w: 0.5, h: 0.5 });
    const v = new DataView(buf);
    expect(v.getUint8(1) & FLAG_CROP).toBe(FLAG_CROP);
    expect([16, 20, 24, 28].map((o) => v.getFloat32(o, true))).toEqual([0.125, 0.25, 0.5, 0.5]);
    expect(new Uint8Array(buf, 32)).toEqual(new Uint8Array(jpeg));
    expect(packFrame(6, 1, jpeg).byteLength).toBe(16 + 4);
  });

  it("frames the table with margins at 16:9, inside the view", () => {
    // a side view: table corners spanning x 400..880, y 380..430 of 1280x720
    const c = tableCrop(
      [
        [400, 400],
        [880, 400],
        [870, 430],
        [410, 380],
      ],
      1280,
      720,
    )!;
    expect(c.x * 1280).toBeLessThan(400 - 0.3 * 480);
    expect((c.x + c.w) * 1280).toBeGreaterThan(880 + 0.3 * 480);
    expect(c.y * 720).toBeLessThan(380 - 0.45 * 480);
    expect((c.w * 1280) / (c.h * 720)).toBeCloseTo(16 / 9, 3);
    expect(c.x >= 0 && c.y >= 0 && c.x + c.w <= 1 + 1e-9 && c.y + c.h <= 1 + 1e-9).toBe(true);
    // a table filling the view: no point cropping
    expect(
      tableCrop(
        [
          [100, 400],
          [1180, 400],
          [1180, 450],
          [100, 450],
        ],
        1280,
        720,
      ),
    ).toBeNull();
  });
});

describe("buildAskContext", () => {
  it("sends the newest calls, scores, rally, server and approved house rules (interfaces-v1 §20)", async () => {
    const { buildAskContext } = await import("../src/lib/askContext.ts");
    const call = (id: string, t: number, status = "final") =>
      ({
        id,
        kind: "point",
        outcome: "out",
        text: "Out",
        p: 0.9,
        tier: "AUTO",
        t_game_s: t,
        status,
        created_at_ms: 1,
      }) as never;
    const ctx = buildAskContext(
      {
        game: {
          t0_ms: 1000,
          rally_no: 4,
          server_team_id: "B",
          teams: [{ team_id: "A", name: "Reds", color: "#f00" }],
        } as never,
        scores: [{ game_id: "g", team_id: "A", points: 7, display: "7", updated_at_ms: 0 }] as never,
        calls: [call("c4", 40), call("c3", 30, "voided"), call("c2", 20), call("c1", 10), call("c0", 0)],
        houseRules: [
          { text: "first to 7", status: "approved" },
          { text: "no lets", status: "pending" },
        ] as never,
      },
      61_000,
    );
    expect(ctx.t_game_s).toBe(60);
    expect(ctx.rally_no).toBe(4);
    expect(ctx.server_team_id).toBe("B");
    expect(ctx.teams).toEqual([{ team_id: "A", name: "Reds" }]);
    expect(ctx.scores[0]).toEqual({ team_id: "A", points: 7, display: "7" });
    expect(ctx.last_calls.map((c) => c.id)).toEqual(["c4", "c2", "c1"]);
    expect(ctx.last_calls[0]).not.toHaveProperty("evidence");
    expect(ctx.house_rules).toEqual([{ text: "first to 7", status: "approved" }]);
  });
});

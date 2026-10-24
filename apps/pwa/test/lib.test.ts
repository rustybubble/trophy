import { describe, expect, it } from "vitest";
import { FLAG_FIRST_AFTER_START, packFrame } from "../src/lib/frame.ts";
import { apply, invert3 } from "../src/lib/homography.ts";
import { parseIntent } from "../src/lib/intent.ts";
import { OnsetDetector } from "../src/lib/onset.ts";

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
    ["add a rule a serve that clips the net is a let", { kind: "house_rule", text: "a serve that clips the net is a let" }],
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

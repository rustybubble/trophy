import { describe, expect, it } from "vitest";
import { upsert } from "../src/lib/useDashboard.ts";
import { TABLE_TENNIS, fitView, onField, toPx } from "../src/lib/world.ts";

describe("world view geometry (interfaces-v1 §3)", () => {
  const v = fitView(TABLE_TENNIS, 520);

  it("puts end A on the left, end B on the right and +y (left facing A→B) at the top", () => {
    const [ax] = toPx(TABLE_TENNIS, v, -1.37, 0);
    const [bx] = toPx(TABLE_TENNIS, v, 1.37, 0);
    const [, top] = toPx(TABLE_TENNIS, v, 0, 0.7625);
    const [, bottom] = toPx(TABLE_TENNIS, v, 0, -0.7625);
    expect(ax).toBeLessThan(bx);
    expect(top).toBeLessThan(bottom);
  });

  it("keeps the table's aspect ratio and fits the width", () => {
    const [x0, y0] = toPx(TABLE_TENNIS, v, -1.37, 0.7625);
    const [x1, y1] = toPx(TABLE_TENNIS, v, 1.37, -0.7625);
    expect((x1 - x0) / (y1 - y0)).toBeCloseTo(2.74 / 1.525, 6);
    expect(v.w).toBe(520);
  });

  it("knows the table edges", () => {
    expect(onField(TABLE_TENNIS, 1.36, 0.76)).toBe(true);
    expect(onField(TABLE_TENNIS, 1.38, 0)).toBe(false);
  });
});

describe("upsert", () => {
  it("replaces by key and prepends new rows", () => {
    const a = [{ id: "1", v: 1 }];
    expect(upsert(a, { id: "1", v: 2 }, (x) => x.id)).toEqual([{ id: "1", v: 2 }]);
    expect(upsert(a, { id: "2", v: 3 }, (x) => x.id).map((x) => x.id)).toEqual(["2", "1"]);
  });
});

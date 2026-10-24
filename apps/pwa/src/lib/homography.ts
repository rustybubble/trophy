// 3x3 row-major helpers for drawing a calibration back onto the still (H maps image px -> field metres).
export type Mat3 = readonly number[];

export function invert3(m: Mat3): number[] {
  const [a, b, c, d, e, f, g, h, i] = m as [number, number, number, number, number, number, number, number, number];
  const A = e * i - f * h;
  const B = -(d * i - f * g);
  const C = d * h - e * g;
  const det = a * A + b * B + c * C;
  if (Math.abs(det) < 1e-12) throw new Error("singular homography");
  return [
    A / det,
    -(b * i - c * h) / det,
    (b * f - c * e) / det,
    B / det,
    (a * i - c * g) / det,
    -(a * f - c * d) / det,
    C / det,
    -(a * h - b * g) / det,
    (a * e - b * d) / det,
  ];
}

export function apply(m: Mat3, x: number, y: number): [number, number] {
  const w = m[6]! * x + m[7]! * y + m[8]!;
  return [(m[0]! * x + m[1]! * y + m[2]!) / w, (m[3]! * x + m[4]! * y + m[5]!) / w];
}

// Table tennis landmarks in tap order (interfaces-v1 §3: origin at the table centre, +x toward end B,
// +y left facing A -> B). "Team A's end first."
export const TABLE_TENNIS = [
  { name: "A_left", pos: [-1.37, 0.7625], prompt: "Team A's end: left corner (as A faces B)" },
  { name: "A_right", pos: [-1.37, -0.7625], prompt: "Team A's end: right corner" },
  { name: "B_right", pos: [1.37, -0.7625], prompt: "Team B's end: right corner (as A faces B)" },
  { name: "B_left", pos: [1.37, 0.7625], prompt: "Team B's end: left corner" },
] as const;

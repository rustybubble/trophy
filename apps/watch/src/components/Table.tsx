// Top-down table tennis table (interfaces-v1 §3: x along the length toward end B, y left facing A→B, metres).
// Everything drawn here is reconstructed from tracking metadata, never video.
import type { ReactNode } from "react";

export const LENGTH = 2.74;
export const WIDTH = 1.525;
const MARGIN = 0.5;
const W = 520;
const SCALE = W / (LENGTH + 2 * MARGIN);
const H = Math.round((WIDTH + 2 * MARGIN) * SCALE);

export const toPx = (x: number, y: number): [number, number] => [
  (x + LENGTH / 2 + MARGIN) * SCALE,
  (WIDTH / 2 + MARGIN - y) * SCALE,
];
export const metres = (m: number) => m * SCALE;

export function Table({ children, label }: { children?: ReactNode; label: string }) {
  const [x0, y0] = toPx(-LENGTH / 2, WIDTH / 2);
  const [x1, y1] = toPx(LENGTH / 2, -WIDTH / 2);
  const [nx] = toPx(0, 0);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="table" role="img" aria-label={label}>
      <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} className="surface" />
      <line x1={x0} y1={(y0 + y1) / 2} x2={x1} y2={(y0 + y1) / 2} className="centre" />
      <line x1={nx} y1={y0 - 6} x2={nx} y2={y1 + 6} className="net" />
      <text x={x0} y={y1 + 18} className="label">
        A
      </text>
      <text x={x1 - 10} y={y1 + 18} className="label">
        B
      </text>
      {children}
    </svg>
  );
}

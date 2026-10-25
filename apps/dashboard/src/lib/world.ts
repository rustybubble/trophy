// Field-frame geometry for the world-state view (interfaces-v1 §3: metres, origin at the table centre, x along the
// length towards team B's end, y across, z up). Pure functions so they can be tested without a DOM.

export interface FieldSpec {
  length: number;
  width: number;
}

/** Regulation table tennis table (ITTF 2.1.2): 2.74 m × 1.525 m. */
export const TABLE_TENNIS: FieldSpec = { length: 2.74, width: 1.525 };

export interface View {
  w: number;
  h: number;
  /** pixels per metre */
  scale: number;
  /** metres of margin drawn around the field */
  margin: number;
}

export function fitView(field: FieldSpec, widthPx: number, margin = 0.6): View {
  const scale = widthPx / (field.length + 2 * margin);
  return { w: widthPx, h: Math.round((field.width + 2 * margin) * scale), scale, margin };
}

/** Field metres (x, y) → SVG pixels; y grows downwards on screen, so team A's left is at the top. */
export function toPx(field: FieldSpec, v: View, x: number, y: number): [number, number] {
  return [(x + field.length / 2 + v.margin) * v.scale, (field.width / 2 + v.margin - y) * v.scale];
}

/** True when a point lies on the table surface (inside the edges). */
export function onField(field: FieldSpec, x: number, y: number): boolean {
  return Math.abs(x) <= field.length / 2 && Math.abs(y) <= field.width / 2;
}

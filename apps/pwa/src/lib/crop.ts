// Phone-side table crop: once the table is known, the camera streams only the region where the ball can be, from
// the full-resolution capture, so the ball gets more pixels in the same 1280x720 frame (D-29).

/** A region of the camera's full view, normalised to 0..1. */
export interface Crop {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * The region to stream for a table seen from the side: the tapped corners' bounding box plus ~1 m beyond each end,
 * ~1.4 m above and a strip below (the table is 2.74 m long; flight's Table.roi uses the same margins), widened to
 * the stream's aspect ratio and kept inside the view. Returns null when that region is most of the view anyway.
 */
export function tableCrop(pts: [number, number][], imgW: number, imgH: number, aspect = 16 / 9): Crop | null {
  if (pts.length < 4 || !imgW || !imgH) return null;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const length = x1 - x0;
  let left = x0 - 0.35 * length;
  let top = Math.min(...ys) - 0.5 * length;
  let w = x1 + 0.35 * length - left;
  let h = Math.max(...ys) + 0.2 * length - top;
  if (w / h < aspect) {
    left -= (h * aspect - w) / 2;
    w = h * aspect;
  } else {
    top -= (w / aspect - h) / 2;
    h = w / aspect;
  }
  if (w > imgW) [w, h] = [imgW, imgW / aspect];
  if (h > imgH) [w, h] = [imgH * aspect, imgH];
  left = Math.min(Math.max(left, 0), imgW - w);
  top = Math.min(Math.max(top, 0), imgH - h);
  if (w > 0.8 * imgW) return null;
  return { x: left / imgW, y: top / imgH, w: w / imgW, h: h / imgH };
}

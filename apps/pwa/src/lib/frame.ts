// The phone -> gateway frame message (interfaces-v1 §5.1): a 16-byte little-endian header, then the JPEG.
//   0 u8 version=1 | 1 u8 flags | 2 u16 reserved | 4 u32 seq | 8 f64 t_capture_phone_ms
// With FLAG_CROP, 16 more bytes (f32 x, y, w, h: the region of the full view this frame shows) precede the JPEG.
import type { Crop } from "./crop.ts";

export const FLAG_CALIB_STILL = 1 << 0;
export const FLAG_FIRST_AFTER_START = 1 << 1;
export const FLAG_CROP = 1 << 2;

export function packFrame(
  seq: number,
  tCapturePhoneMs: number,
  jpeg: ArrayBuffer,
  flags = 0,
  crop?: Crop | null,
): ArrayBuffer {
  const head = crop ? 32 : 16;
  const out = new ArrayBuffer(head + jpeg.byteLength);
  const v = new DataView(out);
  v.setUint8(0, 1);
  v.setUint8(1, crop ? flags | FLAG_CROP : flags & ~FLAG_CROP);
  v.setUint16(2, 0, true);
  v.setUint32(4, seq >>> 0, true);
  v.setFloat64(8, tCapturePhoneMs, true);
  if (crop) [crop.x, crop.y, crop.w, crop.h].forEach((n, i) => v.setFloat32(16 + 4 * i, n, true));
  new Uint8Array(out, head).set(new Uint8Array(jpeg));
  return out;
}

/** Phone clock in epoch ms (interfaces-v1 §2): performance.timeOrigin + a performance-timeline value. */
export function phoneMs(perfTime: number = performance.now()): number {
  return performance.timeOrigin + perfTime;
}

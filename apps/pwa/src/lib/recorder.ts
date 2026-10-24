// Phone-side high-quality recording for challenges. The live stream stays 720p JPEG; in parallel the phone
// records the full-quality camera track in short standalone segments and keeps only the last few. When a
// challenge opens, it uploads just the segments that cover the call's evidence window.
// Restarting MediaRecorder per segment (instead of one long fragmented file) keeps every segment playable on
// its own; the cost is a gap of a few tens of ms between segments.
import { phoneMs } from "./frame.ts";

export interface Segment {
  blob: Blob;
  mime: string;
  tStartPhoneMs: number;
  tEndPhoneMs: number;
  index: number;
}

export const QUALITY = {
  off: null,
  "1080p": { w: 1920, h: 1080, bps: 12_000_000 },
  "4k": { w: 3840, h: 2160, bps: 35_000_000 },
} as const;
export type Quality = keyof typeof QUALITY;

const TYPES = [
  "video/mp4;codecs=avc1.640028",
  "video/mp4;codecs=avc1",
  "video/mp4",
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
];

export function supportedMime(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return TYPES.find((t) => MediaRecorder.isTypeSupported(t));
}

/** Segments overlapping [t0, t1] (phone ms), oldest first. */
export function pickSegments(segments: readonly Segment[], t0: number, t1: number): Segment[] {
  return segments.filter((s) => s.tEndPhoneMs >= t0 && s.tStartPhoneMs <= t1).sort((a, b) => a.index - b.index);
}

export class SegmentRecorder {
  private segments: Segment[] = [];
  private rec: MediaRecorder | undefined;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private index = 0;
  private stopped = true;
  private waiters: { t: number; resolve: () => void }[] = [];
  readonly mime: string;

  constructor(
    private readonly stream: MediaStream,
    private readonly bps: number,
    private readonly segmentMs = 6000,
    private readonly keep = 5,
  ) {
    const mime = supportedMime();
    if (!mime) throw new Error("this browser can't record video");
    this.mime = mime;
  }

  start(): void {
    this.stopped = false;
    this.next();
  }

  stop(): void {
    this.stopped = true;
    clearTimeout(this.timer);
    if (this.rec?.state === "recording") this.rec.stop();
  }

  /** Resolves once a finished segment reaches past `tPhoneMs` (or after `maxWaitMs`). */
  covered(tPhoneMs: number, maxWaitMs = this.segmentMs + 2000): Promise<void> {
    if (this.segments.some((s) => s.tEndPhoneMs >= tPhoneMs)) return Promise.resolve();
    return new Promise((resolve) => {
      const w = { t: tPhoneMs, resolve };
      this.waiters.push(w);
      setTimeout(() => {
        this.waiters = this.waiters.filter((x) => x !== w);
        resolve();
      }, maxWaitMs);
    });
  }

  pick(t0PhoneMs: number, t1PhoneMs: number): Segment[] {
    return pickSegments(this.segments, t0PhoneMs, t1PhoneMs);
  }

  private next(): void {
    if (this.stopped) return;
    const rec = new MediaRecorder(this.stream, { mimeType: this.mime, videoBitsPerSecond: this.bps });
    const chunks: Blob[] = [];
    const index = this.index++;
    let t0 = 0;
    let t1 = 0; // when recording stopped (onstop fires later, once encoding finishes)
    rec.onstart = () => (t0 = phoneMs());
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = () => {
      const seg: Segment = {
        blob: new Blob(chunks, { type: this.mime }),
        mime: this.mime,
        tStartPhoneMs: t0,
        tEndPhoneMs: t1 || phoneMs(),
        index,
      };
      this.segments = [...this.segments, seg].slice(-this.keep);
      const ready = this.waiters.filter((w) => seg.tEndPhoneMs >= w.t);
      this.waiters = this.waiters.filter((w) => seg.tEndPhoneMs < w.t);
      ready.forEach((w) => w.resolve());
    };
    rec.start();
    this.rec = rec;
    this.timer = setTimeout(() => {
      t1 = phoneMs();
      if (rec.state === "recording") rec.stop();
      this.next(); // the next segment starts right away; the old one finishes encoding in the background
    }, this.segmentMs);
  }
}

// JPEG-over-WebSocket frame streamer (interfaces-v1 §5.1): latest frame wins. A frame is encoded only when
// the previous one is done and sent only when ws.bufferedAmount === 0; otherwise it's skipped.
import type { Crop } from "./crop.ts";
import { FLAG_FIRST_AFTER_START, packFrame, phoneMs } from "./frame.ts";

export interface StreamStats {
  connected: boolean;
  sentFps: number;
  skipped: number;
  encodeMs: number;
  kbPerFrame: number;
  w: number;
  h: number;
  /** linear zoom vs streaming the whole view at the same size (1 = uncropped) */
  zoom: number;
}

type VideoWithRvfc = HTMLVideoElement & {
  requestVideoFrameCallback?: (
    cb: (now: number, md: { captureTime?: number; presentationTime: number }) => void,
  ) => number;
};

export class FrameStreamer {
  private ws: WebSocket | undefined;
  private canvas = document.createElement("canvas");
  private g = this.canvas.getContext("2d", { alpha: false })!;
  private seq = 0;
  private busy = false;
  private first = true;
  private stopped = false;
  private sentInWindow = 0;
  private windowStart = performance.now();
  private encodeSum = 0;
  private bytesSum = 0;
  private retry = 500;
  stats: StreamStats = { connected: false, sentFps: 0, skipped: 0, encodeMs: 0, kbPerFrame: 0, w: 0, h: 0, zoom: 1 };
  /** stream only this region of the view (from the full-resolution capture); null = the whole view */
  crop: Crop | null = null;

  constructor(
    private readonly video: VideoWithRvfc,
    private readonly url: string,
    private readonly quality = 0.7,
    private readonly onStats: (s: StreamStats) => void = () => {},
    /** the live stream's size; a larger camera track (recorded for challenges) is scaled down to fit */
    private readonly maxW = 1280,
    private readonly maxH = 720,
  ) {}

  start(): void {
    this.stopped = false;
    this.connect();
    this.loop();
  }

  stop(): void {
    this.stopped = true;
    this.ws?.close();
  }

  private connect(): void {
    const ws = new WebSocket(this.url);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => {
      this.retry = 500;
      this.first = true;
      this.seq = 0;
      this.stats.connected = true;
    };
    ws.onclose = () => {
      this.stats.connected = false;
      if (!this.stopped) setTimeout(() => this.connect(), (this.retry = Math.min(this.retry * 2, 5000)));
    };
    this.ws = ws;
  }

  private loop(): void {
    if (this.stopped) return;
    const v = this.video;
    if (v.requestVideoFrameCallback) {
      v.requestVideoFrameCallback((_now, md) => {
        void this.frame(md.captureTime ?? md.presentationTime);
        this.loop();
      });
    } else {
      requestAnimationFrame((now) => {
        void this.frame(now);
        this.loop();
      });
    }
  }

  private async frame(perfTime: number): Promise<void> {
    const ws = this.ws;
    if (!ws || ws.readyState !== WebSocket.OPEN || this.busy || ws.bufferedAmount > 0) {
      if (ws?.readyState === WebSocket.OPEN) this.stats.skipped++;
      return;
    }
    const vw = this.video.videoWidth;
    const vh = this.video.videoHeight;
    if (!vw || !vh) return;
    const c = this.crop;
    const [sx, sy, sw, sh] = c ? [c.x * vw, c.y * vh, c.w * vw, c.h * vh] : [0, 0, vw, vh];
    const scale = Math.min(1, this.maxW / Math.max(sw, sh), this.maxH / Math.min(sw, sh)); // never upscale
    const w = Math.round(sw * scale);
    const h = Math.round(sh * scale);
    const full = Math.min(1, this.maxW / Math.max(vw, vh), this.maxH / Math.min(vw, vh));
    this.busy = true;
    const t = phoneMs(perfTime);
    try {
      if (this.canvas.width !== w || this.canvas.height !== h) {
        this.canvas.width = w;
        this.canvas.height = h;
      }
      const t0 = performance.now();
      this.g.drawImage(this.video, sx, sy, sw, sh, 0, 0, w, h);
      const blob = await new Promise<Blob | null>((res) => this.canvas.toBlob(res, "image/jpeg", this.quality));
      if (!blob) return;
      const jpeg = await blob.arrayBuffer();
      this.encodeSum += performance.now() - t0;
      this.bytesSum += jpeg.byteLength;
      if (ws.readyState !== WebSocket.OPEN) return;
      ws.send(packFrame(this.seq++, t, jpeg, this.first ? FLAG_FIRST_AFTER_START : 0, c));
      this.first = false;
      this.sentInWindow++;
      this.stats.w = w;
      this.stats.h = h;
      this.stats.zoom = scale / full;
    } finally {
      this.busy = false;
    }
    const now = performance.now();
    if (now - this.windowStart >= 1000) {
      const n = this.sentInWindow || 1;
      this.stats.sentFps = (this.sentInWindow * 1000) / (now - this.windowStart);
      this.stats.encodeMs = this.encodeSum / n;
      this.stats.kbPerFrame = this.bytesSum / n / 1024;
      this.sentInWindow = 0;
      this.encodeSum = 0;
      this.bytesSum = 0;
      this.windowStart = now;
      this.onStats({ ...this.stats });
    }
  }
}

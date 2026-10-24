// Audio onset detector (research card 2D): per 128-sample block, energy vs. an adaptive threshold
// (median + k·MAD over the last ~1 s), with a refractory period. Runs inside an AudioWorklet; pure for tests.
export interface Onset {
  /** sample index (AudioContext frame) of the peak */
  frame: number;
  peak: number;
  energy: number;
}

export class OnsetDetector {
  private ring: Float32Array;
  private n = 0;
  private lastOnsetFrame = -Infinity;
  private thr = Infinity;
  private blocks = 0;

  constructor(
    private readonly sampleRate: number,
    private readonly k = 6,
    private readonly refractoryMs = 60,
    private readonly floor = 2e-6,
    historyBlocks = 375,
  ) {
    this.ring = new Float32Array(historyBlocks);
  }

  /** `start` is the AudioContext frame of x[0]. Returns an onset or null. */
  process(x: Float32Array, start: number): Onset | null {
    let e = 0;
    let peak = 0;
    let at = 0;
    for (let i = 0; i < x.length; i++) {
      const v = x[i]!;
      e += v * v;
      const a = Math.abs(v);
      if (a > peak) {
        peak = a;
        at = i;
      }
    }
    e /= x.length || 1;
    if (this.blocks++ % 16 === 0 && this.n >= 32) this.thr = this.threshold();
    const ready = this.n >= 32;
    let out: Onset | null = null;
    const frame = start + at;
    if (ready && e > this.thr && (frame - this.lastOnsetFrame) * 1000 > this.refractoryMs * this.sampleRate) {
      this.lastOnsetFrame = frame;
      out = { frame, peak, energy: e };
    }
    this.ring[this.n % this.ring.length] = e;
    this.n++;
    return out;
  }

  private threshold(): number {
    const len = Math.min(this.n, this.ring.length);
    const v = Array.from(this.ring.subarray(0, len)).sort((a, b) => a - b);
    const med = v[len >> 1]!;
    const dev = v.map((x) => Math.abs(x - med)).sort((a, b) => a - b);
    const mad = dev[len >> 1]!;
    return Math.max(med + this.k * mad * 1.4826, med * 4, this.floor);
  }
}

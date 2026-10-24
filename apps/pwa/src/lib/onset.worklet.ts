// AudioWorklet: onsets for the gateway (`onset` on /api/ws/ctl). Bundled by Vite (`?worker&url`).
import { OnsetDetector } from "./onset.ts";

declare const sampleRate: number;
declare const currentFrame: number;
declare function registerProcessor(name: string, ctor: unknown): void;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}

class OnsetProcessor extends AudioWorkletProcessor {
  private det = new OnsetDetector(sampleRate);

  process(inputs: Float32Array[][]): boolean {
    const ch = inputs[0]?.[0];
    if (ch) {
      const o = this.det.process(ch, currentFrame);
      if (o) this.port.postMessage({ tc: o.frame / sampleRate, peak: o.peak, energy: o.energy });
    }
    return true;
  }
}

registerProcessor("trophy-onset", OnsetProcessor);

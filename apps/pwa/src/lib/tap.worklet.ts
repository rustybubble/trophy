// AudioWorklet: copies mic blocks to the main thread (push-to-talk -> Ink-2 STT).
declare function registerProcessor(name: string, ctor: unknown): void;
declare class AudioWorkletProcessor {
  readonly port: MessagePort;
}

class TapProcessor extends AudioWorkletProcessor {
  process(inputs: Float32Array[][]): boolean {
    const ch = inputs[0]?.[0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}

registerProcessor("trophy-tap", TapProcessor);
